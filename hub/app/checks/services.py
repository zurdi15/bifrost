"""Reachability of every gateway-routed URL, probed the way a user reaches
it: through the gateway, TLS included.

Results live in memory and are re-probed every sweep — nothing to migrate or
persist. ok/fail transitions publish endpoint.status events (the alert engine
forwards them like any other event), and certificate expiry rides along with
a one-shot warning when it crosses the threshold."""

import asyncio
import logging
import socket
import ssl
import time

import httpx

from app.bus import EventBus
from app.db import session_scope

logger = logging.getLogger("bifrost.checks")

CHECK_INTERVAL_S = 60
CERT_WARN_DAYS = 14

# host → {ok, status, latency_ms, cert_days, checked_at}
results: dict[str, dict] = {}

# Injectable for tests; also disables the real-socket cert probe.
transport: httpx.AsyncBaseTransport | None = None


async def probe(url: str) -> tuple[bool, int | None, float | None]:
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            response = await client.get(url)
        latency = (time.monotonic() - start) * 1000
        return response.status_code < 500, response.status_code, latency
    except httpx.HTTPError:
        return False, None, None


def cert_days_left(host: str, port: int = 443) -> int | None:
    try:
        context = ssl.create_default_context()
        with (
            socket.create_connection((host, port), timeout=5) as sock,
            context.wrap_socket(sock, server_hostname=host) as tls,
        ):
            cert = tls.getpeercert()
        expires = ssl.cert_time_to_seconds(cert["notAfter"])
        return int((expires - time.time()) // 86400)
    except Exception:
        return None


async def sweep_once(bus: EventBus) -> None:
    from app.api.gateway import _diagnose  # runtime import — avoids a cycle

    with session_scope() as session:
        routes, _ = _diagnose(session, None)
    hosts = [r["host"] for r in routes]
    for host in hosts:
        ok, status, latency = await probe(f"https://{host}/")
        cert = None if transport is not None else await asyncio.to_thread(cert_days_left, host)
        previous = results.get(host)
        results[host] = {
            "ok": ok,
            "status": status,
            "latency_ms": round(latency, 1) if latency is not None else None,
            "cert_days": cert,
            "checked_at": int(time.time()),
        }
        if previous is not None and previous["ok"] != ok:
            bus.publish(
                "endpoint.status", {"host": host, "ok": ok, "status": status, "kind": "service"}
            )
        crossed = previous is None or (previous.get("cert_days") or 10**6) > CERT_WARN_DAYS
        if cert is not None and cert <= CERT_WARN_DAYS and crossed:
            bus.publish(
                "endpoint.status", {"host": host, "ok": ok, "kind": "cert", "cert_days": cert}
            )
    for gone in set(results) - set(hosts):
        results.pop(gone, None)


async def service_checks(bus: EventBus) -> None:
    while True:
        try:
            await sweep_once(bus)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("service check sweep failed")
        await asyncio.sleep(CHECK_INTERVAL_S)
