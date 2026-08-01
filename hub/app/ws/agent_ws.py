import asyncio
import contextlib
import hashlib
import logging
import secrets
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select

from app.bus import EventBus
from app.config import settings
from app.db import session_scope
from app.ingest import handlers
from app.ingest import protocol as proto
from app.metrics.store import MetricsStore
from app.models import Node, now_ts
from app.ws.registry import AgentConn, AgentRegistry

logger = logging.getLogger("bifrost.agent_ws")

router = APIRouter()

ACK_EVERY = 10
CLOCK_SKEW_TOLERANCE_S = 30

# Close codes (WebSocket application range)
WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def set_node_status(bus: EventBus, node_uuid: str, status: str) -> None:
    """Persist a status change and publish it. No-op if unchanged."""
    with session_scope() as session:
        node = session.scalar(select(Node).where(Node.uuid == node_uuid))
        if node is None or node.status == status:
            return
        node.status = status
        node.last_seen = now_ts()
    bus.publish("node.status", {"uuid": node_uuid, "status": status})


def _effective_ts(agent_ts: int) -> int:
    """Trust the agent clock only within tolerance; NAS/Pi clocks drift."""
    received = now_ts()
    return agent_ts if abs(received - agent_ts) <= CLOCK_SKEW_TOLERANCE_S else received


@router.websocket("/api/ws/agent")
async def agent_ws(ws: WebSocket) -> None:
    bus: EventBus = ws.app.state.bus
    registry: AgentRegistry = ws.app.state.agent_registry
    metrics: MetricsStore = ws.app.state.metrics

    token = (ws.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    fingerprint = ws.headers.get("x-bifrost-fingerprint", "").strip()
    if not token or not fingerprint:
        await ws.close(code=WS_UNAUTHORIZED)
        return

    await ws.accept()

    try:
        async with asyncio.timeout(10):
            hello = proto.parse_agent_message(await ws.receive_text())
    except (TimeoutError, WebSocketDisconnect):
        return
    except Exception:
        await ws.send_text(proto.ErrorMsg(code="bad_hello").model_dump_json())
        await ws.close(code=WS_FORBIDDEN)
        return

    if not isinstance(hello, proto.Hello) or hello.proto < proto.MIN_PROTO_VERSION:
        await ws.send_text(
            proto.ErrorMsg(
                code="proto_unsupported",
                msg=f"hub speaks proto >= {proto.MIN_PROTO_VERSION}; upgrade the agent image",
            ).model_dump_json()
        )
        await ws.close(code=WS_FORBIDDEN)
        return

    enrolling = secrets.compare_digest(token, settings.enroll_token)
    minted_token: str | None = None

    with session_scope() as session:
        node = session.scalar(select(Node).where(Node.fingerprint == fingerprint))
        if node is None:
            if not enrolling:
                session.rollback()
                await ws.close(code=WS_FORBIDDEN)
                return
            node = Node(
                fingerprint=fingerprint,
                name=hello.hostname or fingerprint[:12],
                hostname=hello.hostname or None,
                kind="agent",
                status="new" if settings.auto_approve else "pending",
                approved_at=now_ts() if settings.auto_approve else None,
            )
            session.add(node)
            session.flush()
        elif not enrolling:
            if node.token_hash is None or sha256_hex(token) != node.token_hash:
                session.rollback()
                await ws.close(code=WS_FORBIDDEN)
                return

        if enrolling:
            # First contact or re-enroll after agent restart: rotate the token.
            minted_token = secrets.token_urlsafe(32)
            node.token_hash = sha256_hex(minted_token)

        if node.status == "pending":
            session.commit()
            await ws.send_text(proto.ErrorMsg(code="pending_approval").model_dump_json())
            await ws.close(code=WS_FORBIDDEN)
            return

        # The name follows the reported hostname unless the user renamed the
        # node (then name != last reported hostname and is left alone). This
        # also heals nodes enrolled before the agent learned to read the
        # host's hostname instead of its container id.
        if hello.hostname and hello.hostname != node.hostname:
            if node.name in (node.hostname, fingerprint[:12]):
                node.name = hello.hostname
            node.hostname = hello.hostname
        node.os = hello.os or node.os
        node.arch = hello.arch or node.arch
        node.agent_version = hello.agent_version or node.agent_version
        node.boot_ts = hello.boot_ts or node.boot_ts
        node.last_seen = now_ts()
        previous_status = node.status
        node.status = "online"
        # Same process reconnecting: resume from what we processed. Fresh
        # process (start_seq below our position): follow the agent — its
        # counter restarted and old frames are gone anyway.
        resume_from = min(node.last_seq, hello.start_seq)
        node.last_seq = resume_from
        node_id, node_uuid = node.id, node.uuid

    if previous_status != "online":
        bus.publish("node.status", {"uuid": node_uuid, "status": "online"})

    await ws.send_text(
        proto.HelloAck(
            node_uuid=node_uuid,
            agent_token=minted_token,
            config=proto.AgentConfig(
                metrics_interval_s=settings.metrics_interval_s,
                fs_interval_s=settings.fs_interval_s,
                smart_interval_s=settings.smart_interval_s,
                heartbeat_interval_s=settings.heartbeat_interval_s,
            ),
            resume_from_seq=resume_from,
        ).model_dump_json()
    )

    conn = AgentConn(node_id=node_id, node_uuid=node_uuid, ws=ws, last_seq=resume_from)
    registry.add(conn)
    logger.info("agent connected: %s (%s)", hello.hostname, node_uuid)

    unacked = 0
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = proto.parse_agent_message(raw)
            except ValidationError:
                # A malformed frame must not kill the connection: the agent
                # would resend it from its ring forever. Skip it — later acks
                # move the agent past it.
                logger.warning("skipping unparseable frame from %s: %.200s", node_uuid, raw)
                continue
            if isinstance(msg, proto.Hello):
                continue

            conn.last_heartbeat = time.monotonic()
            if conn.degraded:
                conn.degraded = False
                set_node_status(bus, node_uuid, "online")

            if isinstance(msg, proto.Heartbeat):
                pass
            elif msg.seq <= conn.last_seq:
                continue  # duplicate after resume
            elif isinstance(msg, proto.Metrics):
                ts = _effective_ts(msg.ts)
                samples = [(s.name, s.value) for s in msg.samples]
                metrics.enqueue(node_id, ts, samples)
                conn.latest.update(dict(samples))
                conn.latest_ts = ts
                conn.last_seq = msg.seq
                bus.publish(
                    "metrics.live",
                    {"uuid": node_uuid, "ts": ts, "samples": dict(samples)},
                )
            elif isinstance(msg, proto.Fs):
                with session_scope() as session:
                    serialized_mounts = handlers.apply_fs(session, node_id, msg.mounts)
                conn.last_seq = msg.seq
                # Feed usage into history so capacity trends are queryable.
                ts = _effective_ts(msg.ts)
                fs_samples = [
                    (f"fs.{m['mountpoint']}.used_pct", m["used_pct"])
                    for m in serialized_mounts
                    if m["used_pct"] is not None and not m["stale"]
                ]
                if fs_samples:
                    metrics.enqueue(node_id, ts, fs_samples)
                bus.publish("fs.updated", {"uuid": node_uuid, "mounts": serialized_mounts})
            elif isinstance(msg, proto.Smart):
                with session_scope() as session:
                    rows = handlers.apply_smart(session, node_id, msg.disks)
                    db_node = session.get(Node, node_id)
                    node_name = db_node.name if db_node else ""
                    serialized_disks = [
                        handlers.serialize_disk(d, node_uuid, node_name) for d in rows
                    ]
                conn.last_seq = msg.seq
                # Disk temperature history (per serial).
                ts = _effective_ts(msg.ts)
                disk_samples = [
                    (f"disk.{d['serial']}.temp", d["temp_c"])
                    for d in serialized_disks
                    if d["temp_c"] is not None
                ]
                if disk_samples:
                    metrics.enqueue(node_id, ts, disk_samples)
                bus.publish("disk.updated", {"uuid": node_uuid, "disks": serialized_disks})
            elif isinstance(msg, proto.ContainersFull):
                with session_scope() as session:
                    handlers.apply_containers_full(session, node_id, msg.containers)
                    db_node = session.get(Node, node_id)
                    serialized = handlers.list_node_containers(
                        session, node_id, node_uuid, db_node.name if db_node else ""
                    )
                conn.last_seq = msg.seq
                bus.publish(
                    "containers.updated", {"uuid": node_uuid, "containers": serialized}
                )
            elif isinstance(msg, proto.ContainerStats):
                with session_scope() as session:
                    handlers.apply_container_stats(session, node_id, msg.stats)
                    db_node = session.get(Node, node_id)
                    serialized = handlers.list_node_containers(
                        session, node_id, node_uuid, db_node.name if db_node else ""
                    )
                conn.last_seq = msg.seq
                bus.publish(
                    "containers.updated", {"uuid": node_uuid, "containers": serialized}
                )
            elif isinstance(msg, proto.ContainerEvent):
                conn.last_seq = msg.seq
                bus.publish(
                    "container.event",
                    {
                        "uuid": node_uuid,
                        "action": msg.action,
                        "name": msg.container.name,
                        "image": msg.container.image,
                    },
                )
            elif isinstance(msg, proto.K8sDetected):
                conn.last_seq = msg.seq
                from app.k8s.discovery import register_discovered_cluster

                node_address = ws.client.host if ws.client else ""
                with session_scope() as session:
                    db_node = session.get(Node, node_id)
                    if db_node is not None:
                        cluster, created = register_discovered_cluster(
                            session, db_node, msg, node_address
                        )
                        cluster_info = {
                            "id": cluster.id,
                            "name": cluster.name,
                            "distro": msg.distro,
                            "node": node_uuid,
                            "created": created,
                        }
                    else:
                        cluster_info = None
                if cluster_info:
                    bus.publish("k8s.cluster.discovered", cluster_info)
                    manager = getattr(ws.app.state, "k8s_manager", None)
                    if manager is not None:
                        manager.request_refresh()
            else:
                # fs / containers / smart / k8s_detected land in later phases;
                # advance seq so resume never replays them at us forever.
                conn.last_seq = msg.seq

            unacked += 1
            if unacked >= ACK_EVERY:
                unacked = 0
                await ws.send_text(proto.Ack(upto_seq=conn.last_seq).model_dump_json())
                with session_scope() as session:
                    db_node = session.get(Node, node_id)
                    if db_node is not None:
                        db_node.last_seq = conn.last_seq
                        db_node.last_seen = now_ts()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("agent connection error: %s", node_uuid)
    finally:
        registry.remove(conn)
        with session_scope() as session:
            db_node = session.get(Node, node_id)
            if db_node is not None:
                db_node.last_seq = conn.last_seq
        # A reconnect may already have replaced us; only then skip the offline mark.
        if registry.get(node_uuid) is None:
            set_node_status(bus, node_uuid, "offline")
            logger.info("agent disconnected: %s", node_uuid)


async def heartbeat_monitor(app_state) -> None:  # noqa: ANN001
    """Catch half-open TCP: socket close is instant, this covers silent death.
    2 missed heartbeats → degraded, 3 → offline (socket force-closed)."""
    bus: EventBus = app_state.bus
    registry: AgentRegistry = app_state.agent_registry
    interval = settings.heartbeat_interval_s
    while True:
        await asyncio.sleep(interval / 3)
        deadline_degraded = interval * 2
        deadline_offline = interval * 3
        for conn in registry.all():
            silent_for = time.monotonic() - conn.last_heartbeat
            if silent_for > deadline_offline:
                registry.remove(conn)
                set_node_status(bus, conn.node_uuid, "offline")
                with contextlib.suppress(Exception):
                    await conn.ws.close()
            elif silent_for > deadline_degraded and not conn.degraded:
                conn.degraded = True
                set_node_status(bus, conn.node_uuid, "degraded")
