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

SCHEMA_VERSION = 2

FLUSH_INTERVAL_S = 5.0
FLUSH_MAX_ROWS = 500

_SCHEMA_V1 = """
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

# Downsampler bookkeeping (watermarks of last aggregated bucket).
_SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL
);
"""

_MIGRATIONS = {1: _SCHEMA_V1, 2: _SCHEMA_V2}

Row = tuple[int, int, int, float]  # node_id, metric_id, ts, value

# Buckets are aggregated once they are safely in the past (late frames from
# ring resends may still land inside the lag window).
DOWNSAMPLE_LAG_S = 120
MAINTENANCE_INTERVAL_S = 60.0
RETENTION_INTERVAL_S = 3600

DEFAULT_RETENTION = {
    "raw": 24 * 3600,
    "1m": 14 * 86400,
    "1h": 730 * 86400,
}


class MetricsStore:
    def __init__(self, path: Path, retention: dict[str, int] | None = None) -> None:
        self._path = path
        self._retention = {**DEFAULT_RETENTION, **(retention or {})}
        self._conn: sqlite3.Connection | None = None
        self._queue: asyncio.Queue[tuple[int, int, list[tuple[str, float]]]] = asyncio.Queue(
            maxsize=10_000
        )
        self._names: dict[str, int] = {}
        self._writer: asyncio.Task | None = None
        self._maintenance: asyncio.Task | None = None
        self._flush_event = asyncio.Event()
        self._flush_done = asyncio.Event()

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await asyncio.to_thread(self._open_sync)
        self._writer = asyncio.create_task(self._writer_loop(), name="metrics-writer")
        self._maintenance = asyncio.create_task(
            self._maintenance_loop(), name="metrics-maintenance"
        )

    async def stop(self) -> None:
        for task in (self._writer, self._maintenance):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await asyncio.to_thread(self._drain_and_close_sync)

    def _open_sync(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        while version < SCHEMA_VERSION:
            version += 1
            conn.executescript(_MIGRATIONS[version])
            conn.execute(f"PRAGMA user_version={version}")
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

    # ── downsampling & retention ─────────────────────────────────────────────

    def _meta_get_sync(self, key: str, default: int = 0) -> int:
        assert self._conn is not None
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _meta_set_sync(self, key: str, value: int) -> None:
        assert self._conn is not None
        self._conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, value))

    def downsample_once_sync(self, now: int | None = None) -> None:
        """Aggregate completed buckets: raw → 1m, then 1m → 1h. Idempotent
        (INSERT OR REPLACE + watermarks in meta)."""
        assert self._conn is not None
        now = now or int(time.time())
        with self._conn:
            cutoff_1m = (now - DOWNSAMPLE_LAG_S) // 60 * 60
            start_1m = self._meta_get_sync("agg_1m_upto")
            if cutoff_1m > start_1m:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO samples_1m
                    SELECT node_id, metric_id, (ts/60)*60,
                           avg(value), min(value), max(value), count(*)
                    FROM samples_raw WHERE ts >= ? AND ts < ?
                    GROUP BY node_id, metric_id, ts/60
                    """,
                    (start_1m, cutoff_1m),
                )
                self._meta_set_sync("agg_1m_upto", cutoff_1m)

            cutoff_1h = (now - DOWNSAMPLE_LAG_S) // 3600 * 3600
            start_1h = self._meta_get_sync("agg_1h_upto")
            if cutoff_1h > start_1h:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO samples_1h
                    SELECT node_id, metric_id, (ts/3600)*3600,
                           sum(avg*n)/sum(n), min(min), max(max), sum(n)
                    FROM samples_1m WHERE ts >= ? AND ts < ?
                    GROUP BY node_id, metric_id, ts/3600
                    """,
                    (start_1h, cutoff_1h),
                )
                self._meta_set_sync("agg_1h_upto", cutoff_1h)

    def apply_retention_sync(self, now: int | None = None) -> None:
        assert self._conn is not None
        now = now or int(time.time())
        with self._conn:
            for table, key in (
                ("samples_raw", "raw"),
                ("samples_1m", "1m"),
                ("samples_1h", "1h"),
            ):
                self._conn.execute(
                    f"DELETE FROM {table} WHERE ts < ?",  # noqa: S608 — fixed table names
                    (now - self._retention[key],),
                )
        self._conn.execute("PRAGMA optimize")

    async def _maintenance_loop(self) -> None:
        last_retention = 0.0
        while True:
            await asyncio.sleep(MAINTENANCE_INTERVAL_S)
            try:
                await asyncio.to_thread(self.downsample_once_sync)
                if time.monotonic() - last_retention > RETENTION_INTERVAL_S:
                    last_retention = time.monotonic()
                    await asyncio.to_thread(self.apply_retention_sync)
            except Exception:  # pragma: no cover — never kill the loop
                import logging

                logging.getLogger("bifrost.metrics").exception("maintenance cycle failed")

    # ── query ────────────────────────────────────────────────────────────────

    @staticmethod
    def pick_resolution(from_ts: int, to_ts: int) -> str:
        span = to_ts - from_ts
        if span <= 6 * 3600:
            return "raw"
        if span <= 15 * 86400:
            return "1m"
        return "1h"

    def query_sync(
        self, node_id: int, names: list[str], from_ts: int, to_ts: int, res: str = "auto"
    ) -> tuple[str, dict[str, list]]:
        """Series query on a read-only connection; call via asyncio.to_thread.

        Raw rows are [ts, value]; aggregated rows are [ts, avg, min, max]."""
        if res == "auto":
            res = self.pick_resolution(from_ts, to_ts)
        conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            result: dict[str, list] = {}
            for name in names:
                row = conn.execute("SELECT id FROM metric_defs WHERE name=?", (name,)).fetchone()
                if row is None:
                    result[name] = []
                    continue
                if res == "raw":
                    result[name] = [
                        list(r)
                        for r in conn.execute(
                            "SELECT ts, value FROM samples_raw"
                            " WHERE node_id=? AND metric_id=? AND ts BETWEEN ? AND ? ORDER BY ts",
                            (node_id, row[0], from_ts, to_ts),
                        )
                    ]
                else:
                    table = "samples_1m" if res == "1m" else "samples_1h"
                    result[name] = [
                        list(r)
                        for r in conn.execute(
                            f"SELECT ts, avg, min, max FROM {table}"  # noqa: S608
                            " WHERE node_id=? AND metric_id=? AND ts BETWEEN ? AND ? ORDER BY ts",
                            (node_id, row[0], from_ts, to_ts),
                        )
                    ]
            return res, result
        finally:
            conn.close()
