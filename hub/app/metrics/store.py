"""Time-series storage over metrics.db.

A single writer task owns the write connection: samples are enqueued from the
agent WebSocket handlers and flushed in one transaction every FLUSH_INTERVAL_S
or FLUSH_MAX_ROWS, whichever comes first. SQLite is fast with large batched
transactions and pathological with row-at-a-time writes — never write to this
database from request handlers.

Reads open their own short-lived connections (WAL allows concurrent readers).
Schema is managed in code via PRAGMA user_version (not Alembic — this file has
churn Alembic should never touch).
"""

import asyncio
import contextlib
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 1

FLUSH_INTERVAL_S = 5.0
FLUSH_MAX_ROWS = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_defs (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS samples_raw (
  node_id INTEGER NOT NULL,
  metric_id INTEGER NOT NULL,
  ts INTEGER NOT NULL,
  value REAL NOT NULL,
  PRIMARY KEY (node_id, metric_id, ts)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS samples_1m (
  node_id INTEGER NOT NULL,
  metric_id INTEGER NOT NULL,
  ts INTEGER NOT NULL,
  avg REAL NOT NULL, min REAL NOT NULL, max REAL NOT NULL, n INTEGER NOT NULL,
  PRIMARY KEY (node_id, metric_id, ts)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS samples_1h (
  node_id INTEGER NOT NULL,
  metric_id INTEGER NOT NULL,
  ts INTEGER NOT NULL,
  avg REAL NOT NULL, min REAL NOT NULL, max REAL NOT NULL, n INTEGER NOT NULL,
  PRIMARY KEY (node_id, metric_id, ts)
) WITHOUT ROWID;
"""

Row = tuple[int, int, int, float]  # node_id, metric_id, ts, value


class MetricsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self._queue: asyncio.Queue[tuple[int, int, list[tuple[str, float]]]] = asyncio.Queue(
            maxsize=10_000
        )
        self._names: dict[str, int] = {}
        self._writer: asyncio.Task | None = None
        self._flush_event = asyncio.Event()
        self._flush_done = asyncio.Event()

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await asyncio.to_thread(self._open_sync)
        self._writer = asyncio.create_task(self._writer_loop(), name="metrics-writer")

    async def stop(self) -> None:
        if self._writer:
            self._writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer
        await asyncio.to_thread(self._drain_and_close_sync)

    def _open_sync(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version < SCHEMA_VERSION:
            conn.executescript(_SCHEMA)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.commit()
        self._names = dict(conn.execute("SELECT name, id FROM metric_defs").fetchall())
        self._conn = conn

    def _drain_and_close_sync(self) -> None:
        rows: list[Row] = []
        while not self._queue.empty():
            node_id, ts, samples = self._queue.get_nowait()
            rows.extend(self._to_rows_sync(node_id, ts, samples))
        if self._conn:
            if rows:
                self._flush_sync(rows)
            self._conn.close()
            self._conn = None

    # ── ingest ───────────────────────────────────────────────────────────────

    def enqueue(self, node_id: int, ts: int, samples: list[tuple[str, float]]) -> None:
        try:
            self._queue.put_nowait((node_id, ts, samples))
        except asyncio.QueueFull:
            # Backpressure: drop the oldest batch, keep the freshest data.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self._queue.put_nowait((node_id, ts, samples))

    async def flush_now(self) -> None:
        """Force a flush cycle (tests, graceful shutdown)."""
        self._flush_done.clear()
        self._flush_event.set()
        await self._flush_done.wait()

    async def _writer_loop(self) -> None:
        pending: list[Row] = []
        deadline = time.monotonic() + FLUSH_INTERVAL_S
        while True:
            timeout = max(deadline - time.monotonic(), 0.05)
            try:
                async with asyncio.timeout(timeout):
                    if self._flush_event.is_set():
                        raise TimeoutError
                    node_id, ts, samples = await self._queue.get()
                    rows = await asyncio.to_thread(self._to_rows_sync, node_id, ts, samples)
                    pending.extend(rows)
            except TimeoutError:
                pass
            forced = self._flush_event.is_set()
            if pending and (
                forced or len(pending) >= FLUSH_MAX_ROWS or time.monotonic() >= deadline
            ):
                batch, pending = pending, []
                await asyncio.to_thread(self._flush_sync, batch)
            if time.monotonic() >= deadline:
                deadline = time.monotonic() + FLUSH_INTERVAL_S
            if forced:
                self._flush_event.clear()
                self._flush_done.set()

    def _to_rows_sync(self, node_id: int, ts: int, samples: list[tuple[str, float]]) -> list[Row]:
        return [(node_id, self._intern_sync(name), ts, value) for name, value in samples]

    def _intern_sync(self, name: str) -> int:
        metric_id = self._names.get(name)
        if metric_id is not None:
            return metric_id
        assert self._conn is not None
        self._conn.execute("INSERT OR IGNORE INTO metric_defs(name) VALUES (?)", (name,))
        self._conn.commit()
        metric_id = self._conn.execute(
            "SELECT id FROM metric_defs WHERE name=?", (name,)
        ).fetchone()[0]
        self._names[name] = metric_id
        return metric_id

    def _flush_sync(self, rows: list[Row]) -> None:
        assert self._conn is not None
        with self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO samples_raw(node_id, metric_id, ts, value)"
                " VALUES (?,?,?,?)",
                rows,
            )

    # ── query ────────────────────────────────────────────────────────────────

    def query_sync(
        self, node_id: int, names: list[str], from_ts: int, to_ts: int
    ) -> dict[str, list[tuple[int, float]]]:
        """Raw-resolution query. Runs on its own read-only connection; call via
        asyncio.to_thread from endpoints. Downsampled resolutions arrive in F3."""
        conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            result: dict[str, list[tuple[int, float]]] = {}
            for name in names:
                row = conn.execute("SELECT id FROM metric_defs WHERE name=?", (name,)).fetchone()
                if row is None:
                    result[name] = []
                    continue
                result[name] = conn.execute(
                    "SELECT ts, value FROM samples_raw"
                    " WHERE node_id=? AND metric_id=? AND ts BETWEEN ? AND ? ORDER BY ts",
                    (node_id, row[0], from_ts, to_ts),
                ).fetchall()
            return result
        finally:
            conn.close()
