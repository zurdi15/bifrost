"""Tailnet poller: devices + ACL policy → an in-memory graph snapshot.

Same shape as the image-update watcher: module state re-derived on every
sweep, nothing to migrate, transition-only bus publishes. The REST layer
serves the last good snapshot with any fetch error stapled on top, so a
flaky admin API degrades to a stale-but-visible map, never a blank section."""

import asyncio
import logging
import time

from app.bus import EventBus
from app.config import settings
from app.tailnet import client
from app.tailnet.acl import build_edges
from app.tailnet.model import map_device

logger = logging.getLogger("bifrost.tailnet")

INTERVAL_S = 60
STARTUP_DELAY_S = 5

snapshot: dict | None = None
error: str | None = None
# device id → online at the previous sweep; None until one completes, so a
# hub restart never fires a storm of online events.
_online: dict[str, bool] | None = None


def configured() -> bool:
    return bool(settings.tailscale_api_key) or settings.tailnet_fixture is not None


def current() -> dict:
    base = {"configured": configured(), "error": error}
    if snapshot is None:
        return {
            **base,
            "source": "",
            "tailnet": "",
            "fetched_at": 0,
            "devices": [],
            "edges": [],
            "internet": False,
            "policy": None,
        }
    return {**base, **snapshot}


async def sweep_once(bus: EventBus | None = None) -> None:
    global snapshot, error, _online
    if not configured():
        snapshot = None
        error = None
        _online = None
        return
    try:
        if settings.tailnet_fixture is not None:
            raw_devices, policy, tailnet_name = await client.load_fixture(
                settings.tailnet_fixture
            )
            source = "fixture"
        else:
            raw_devices, policy = await client.fetch(
                settings.tailscale_api_key, settings.tailscale_tailnet
            )
            tailnet_name, source = settings.tailscale_tailnet, "api"
    except Exception as exc:
        error = str(exc)
        logger.warning("tailnet sweep failed: %s", exc)
        return
    error = None

    now = int(time.time())
    devices = sorted((map_device(raw, now) for raw in raw_devices), key=lambda d: d.name)
    if tailnet_name in ("", "-") and devices:
        # The API key's own tailnet has no name of record here; the device
        # MagicDNS suffix is the honest label.
        tailnet_name = devices[0].fqdn.partition(".")[2] or "-"
    edges, unresolved, internet_used = build_edges(policy, devices)

    fresh = {
        "source": source,
        "tailnet": tailnet_name,
        "fetched_at": now,
        "devices": [d.as_dict() for d in devices],
        "edges": edges,
        "internet": internet_used,
        "policy": {
            "rules": len(policy.get("acls") or []) + len(policy.get("grants") or []),
            "groups": {name: len(v or []) for name, v in (policy.get("groups") or {}).items()},
            "unresolved": sorted(unresolved),
        },
    }

    online_now = {d.id: d.online for d in devices}
    if bus is not None and _online is not None:
        names = {d.id: d.name for d in devices}
        for dev_id, is_online in online_now.items():
            was = _online.get(dev_id)
            if was is not None and was != is_online:
                topic = "tailnet.device." + ("online" if is_online else "offline")
                bus.publish(topic, {"subject": names[dev_id], "device": dev_id})

    changed = snapshot is None or {**snapshot, "fetched_at": 0} != {**fresh, "fetched_at": 0}
    _online = online_now
    snapshot = fresh
    if changed and bus is not None:
        bus.publish("tailnet.updated", {"devices": len(devices), "edges": len(edges)})


async def tailnet_poll(bus: EventBus) -> None:
    await asyncio.sleep(STARTUP_DELAY_S)
    while True:
        try:
            await sweep_once(bus)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("tailnet sweep failed")
        await asyncio.sleep(INTERVAL_S)
