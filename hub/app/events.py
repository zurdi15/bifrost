import asyncio
import json
import logging

from sqlalchemy import select

from app.bus import EventBus
from app.db import session_scope
from app.models import DbEvent, Node

logger = logging.getLogger("bifrost.events")

# Topics worth keeping in the timeline. Live metric frames are never persisted
# here — they go to metrics.db.
PERSISTED_TOPICS = {
    "node.status": "info",
    "container.event": "info",
    "k8s.cronjob.run": "info",
    "disk.updated": "info",
    "endpoint.status": "info",
    "k8s.cluster.discovered": "info",
    "tailnet.device.online": "info",
    "tailnet.device.offline": "info",
}


def _severity(topic: str, data: dict) -> str:
    if topic == "node.status" and data.get("status") in ("offline", "degraded"):
        return "warning"
    if topic == "k8s.cronjob.run" and not data.get("succeeded"):
        return "warning"
    if topic == "endpoint.status" and (
        not data.get("ok", True) or data.get("kind") == "cert"
    ):
        return "warning"
    if topic == "disk.updated" and any(
        d.get("smart_status") == "failed" for d in data.get("disks", [])
    ):
        return "warning"
    if topic == "tailnet.device.offline":
        return "warning"
    return PERSISTED_TOPICS.get(topic, "info")


def _record_sync(topic: str, data: dict, ts: int) -> None:
    with session_scope() as session:
        node_id = None
        if "uuid" in data:
            node = session.scalar(select(Node).where(Node.uuid == data["uuid"]))
            node_id = node.id if node else None
        session.add(
            DbEvent(
                ts=ts,
                kind=topic,
                severity=_severity(topic, data),
                node_id=node_id,
                subject=data.get("uuid") or data.get("subject"),
                payload_json=json.dumps(data),
            )
        )


async def events_recorder(bus: EventBus) -> None:
    """EventBus subscriber persisting the timeline. Runs for the app's lifetime."""
    queue = bus.subscribe()
    try:
        while True:
            event = await queue.get()
            if event.topic not in PERSISTED_TOPICS:
                continue
            try:
                await asyncio.to_thread(_record_sync, event.topic, event.data, event.ts)
            except Exception:
                logger.exception("failed to record event %s", event.topic)
    finally:
        bus.unsubscribe(queue)
