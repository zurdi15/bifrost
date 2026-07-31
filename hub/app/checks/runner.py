"""Agentless endpoint checks (ping/http/tcp) run from the hub.

This is how boxes that can't run containers (Home Assistant OS, routers) get
up/down + latency monitoring. Check latency also lands in metrics history as
check.latency_ms per node.
"""

import asyncio
import contextlib
import logging
import shutil
import time

import httpx
from sqlalchemy import select

from app.bus import EventBus
from app.db import session_scope
from app.metrics.store import MetricsStore
from app.models import EndpointCheck, Node, now_ts
from app.ws.agent_ws import set_node_status

logger = logging.getLogger("bifrost.checks")

SCAN_INTERVAL_S = 5


async def run_http_check(
    target: str,
    timeout_s: int,
    expect_status: int | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[bool, float | None]:
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=timeout_s, verify=False, transport=transport
        ) as client:
            response = await client.get(target)
        latency = (time.monotonic() - start) * 1000
        ok = response.status_code == expect_status if expect_status else response.status_code < 500
        return ok, latency
    except httpx.HTTPError:
        return False, None


async def run_tcp_check(target: str, timeout_s: int) -> tuple[bool, float | None]:
    host, _, port = target.rpartition(":")
    if not host or not port.isdigit():
        return False, None
    start = time.monotonic()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port)), timeout=timeout_s
        )
        latency = (time.monotonic() - start) * 1000
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return True, latency
    except (TimeoutError, OSError):
        return False, None


async def run_ping_check(target: str, timeout_s: int) -> tuple[bool, float | None]:
    """System ping when available (ICMP needs privileges the container may
    lack); otherwise falls back to a TCP dial on port 80/443."""
    if shutil.which("ping"):
        start = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(timeout_s), target,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        code = await process.wait()
        if code == 0:
            return True, (time.monotonic() - start) * 1000
        return False, None
    for port in (443, 80):
        ok, latency = await run_tcp_check(f"{target}:{port}", timeout_s)
        if ok:
            return ok, latency
    return False, None


async def run_check(
    kind: str,
    target: str,
    timeout_s: int,
    expect_status: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[bool, float | None]:
    if kind == "http":
        return await run_http_check(target, timeout_s, expect_status, transport)
    if kind == "tcp":
        return await run_tcp_check(target, timeout_s)
    if kind == "ping":
        return await run_ping_check(target, timeout_s)
    return False, None


async def _execute_due_checks(bus: EventBus, metrics: MetricsStore) -> None:
    now = now_ts()
    with session_scope() as session:
        due = [
            (c.id, c.node_id, c.check_kind, c.target, c.timeout_s, c.expect_status)
            for c in session.scalars(select(EndpointCheck)).all()
            if (c.last_checked or 0) + c.interval_s <= now
        ]
    if not due:
        return

    results = await asyncio.gather(
        *(run_check(kind, target, timeout, expect) for _, _, kind, target, timeout, expect in due)
    )

    node_ids = set()
    with session_scope() as session:
        for (check_id, node_id, _, _, _, _), (ok, latency) in zip(due, results, strict=True):
            check = session.get(EndpointCheck, check_id)
            if check is None:
                continue
            check.last_ok = ok
            check.last_latency_ms = latency
            check.last_checked = now
            node_ids.add(node_id)

    # A node is up while any of its checks passes. set_node_status opens its
    # own session, so evaluate per node outside the write transaction.
    for node_id in node_ids:
        with session_scope() as session:
            node = session.get(Node, node_id)
            if node is None or node.kind != "endpoint":
                continue
            node.last_seen = now
            evaluated = [
                c
                for c in session.scalars(
                    select(EndpointCheck).where(EndpointCheck.node_id == node_id)
                )
                if c.last_checked
            ]
            if not evaluated:
                continue
            any_ok = any(c.last_ok for c in evaluated)
            uuid = node.uuid
            latencies = [
                c.last_latency_ms for c in evaluated if c.last_ok and c.last_latency_ms
            ]
        set_node_status(bus, uuid, "online" if any_ok else "offline")
        if latencies:
            metrics.enqueue(node_id, now, [("check.latency_ms", min(latencies))])
        bus.publish(
            "endpoint.status",
            {"uuid": uuid, "ok": any_ok, "latency_ms": min(latencies) if latencies else None},
        )


async def checks_runner(app_state) -> None:  # noqa: ANN001
    bus: EventBus = app_state.bus
    metrics: MetricsStore = app_state.metrics
    while True:
        await asyncio.sleep(SCAN_INTERVAL_S)
        try:
            await _execute_due_checks(bus, metrics)
        except Exception:
            logger.exception("check cycle failed")
