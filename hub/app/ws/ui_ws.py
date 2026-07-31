import asyncio
import contextlib
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.bus import EventBus

logger = logging.getLogger("bifrost.ui_ws")

router = APIRouter()

# Live metric frames are throttled per node per connection; everything else
# (status changes, events) is always forwarded immediately.
METRICS_THROTTLE_S = 5.0

TOPIC_CATEGORY = {
    "metrics.live": "metrics",
    "node.status": "nodes",
}


@router.websocket("/api/ws/ui")
async def ui_ws(ws: WebSocket) -> None:
    bus: EventBus = ws.app.state.bus
    await ws.accept()

    subscriptions: set[str] = {"metrics", "nodes", "events"}
    queue = bus.subscribe()
    last_metric_sent: dict[str, float] = {}

    async def sender() -> None:
        while True:
            event = await queue.get()
            category = TOPIC_CATEGORY.get(event.topic, "events")
            if category not in subscriptions:
                continue
            if event.topic == "metrics.live":
                node_uuid = event.data.get("uuid", "")
                now = time.monotonic()
                if now - last_metric_sent.get(node_uuid, 0.0) < METRICS_THROTTLE_S:
                    continue
                last_metric_sent[node_uuid] = now
            await ws.send_text(
                json.dumps({"seq": event.seq, "topic": event.topic, "data": event.data})
            )

    async def receiver() -> None:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg.get("sub"), list):
                subscriptions.clear()
                subscriptions.update(str(s) for s in msg["sub"])
            if msg.get("ping"):
                await ws.send_text(json.dumps({"pong": True, "seq": bus.seq}))

    sender_task = asyncio.create_task(sender())
    try:
        await receiver()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ui connection error")
    finally:
        sender_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender_task
        bus.unsubscribe(queue)
