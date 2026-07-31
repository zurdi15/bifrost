import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Node, now_ts
from app.ws.registry import AgentRegistry

router = APIRouter()


def node_to_dict(node: Node, registry: AgentRegistry, checks: list | None = None) -> dict:
    conn = registry.get(node.uuid)
    return {
        "checks": checks,
        "uuid": node.uuid,
        "name": node.name,
        "kind": node.kind,
        "status": node.status,
        "os": node.os,
        "arch": node.arch,
        "agent_version": node.agent_version,
        "boot_ts": node.boot_ts,
        "labels": json.loads(node.labels_json or "{}"),
        "last_seen": node.last_seen,
        "created_at": node.created_at,
        "live": (
            {"ts": conn.latest_ts, "samples": dict(conn.latest)} if conn is not None else None
        ),
    }


def _checks_for(session: Session, node: Node) -> list | None:
    if node.kind != "endpoint":
        return None
    from app.models import EndpointCheck

    return [
        {
            "id": c.id,
            "kind": c.check_kind,
            "target": c.target,
            "interval_s": c.interval_s,
            "last_ok": c.last_ok,
            "last_latency_ms": c.last_latency_ms,
            "last_checked": c.last_checked,
        }
        for c in session.scalars(
            select(EndpointCheck).where(EndpointCheck.node_id == node.id)
        )
    ]


@router.get("/nodes")
def list_nodes(request: Request, session: Session = Depends(get_session)) -> list[dict]:
    registry: AgentRegistry = request.app.state.agent_registry
    nodes = session.scalars(select(Node).order_by(Node.created_at)).all()
    return [node_to_dict(n, registry, _checks_for(session, n)) for n in nodes]


@router.get("/snapshot")
def snapshot(request: Request, session: Session = Depends(get_session)) -> dict:
    """Initial UI state: everything the dashboard needs plus the bus seq, so the
    WS client can detect gaps and know when to re-snapshot."""
    from app.api.containers import containers_by_node
    from app.api.disks import disks_by_node
    from app.api.k8s import k8s_services_list

    registry: AgentRegistry = request.app.state.agent_registry
    nodes = session.scalars(select(Node).order_by(Node.created_at)).all()
    return {
        "seq": request.app.state.bus.seq,
        "nodes": [node_to_dict(n, registry, _checks_for(session, n)) for n in nodes],
        "containers": containers_by_node(session),
        "disks": disks_by_node(session),
        "k8s_services": k8s_services_list(session),
    }


def _get_node(session: Session, uuid: str) -> Node:
    node = session.scalar(select(Node).where(Node.uuid == uuid))
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node


@router.get("/nodes/{uuid}")
def get_node(uuid: str, request: Request, session: Session = Depends(get_session)) -> dict:
    registry: AgentRegistry = request.app.state.agent_registry
    node = _get_node(session, uuid)
    return node_to_dict(node, registry, _checks_for(session, node))


class EndpointCheckSpec(BaseModel):
    kind: str  # 'ping' | 'http' | 'tcp'
    target: str
    interval_s: int = 30
    timeout_s: int = 5
    expect_status: int | None = None


class EndpointCreate(BaseModel):
    name: str
    checks: list[EndpointCheckSpec]


@router.post("/nodes/endpoints", status_code=201)
def create_endpoint(
    body: EndpointCreate, request: Request, session: Session = Depends(get_session)
) -> dict:
    from app.models import EndpointCheck

    if not body.checks:
        raise HTTPException(status_code=422, detail="at least one check required")
    for check in body.checks:
        if check.kind not in ("ping", "http", "tcp"):
            raise HTTPException(status_code=422, detail=f"unknown check kind {check.kind}")
    node = Node(name=body.name, kind="endpoint", fingerprint=None, status="new")
    session.add(node)
    session.flush()
    for check in body.checks:
        session.add(
            EndpointCheck(
                node_id=node.id,
                check_kind=check.kind,
                target=check.target,
                interval_s=check.interval_s,
                timeout_s=check.timeout_s,
                expect_status=check.expect_status,
            )
        )
    session.flush()
    registry: AgentRegistry = request.app.state.agent_registry
    return node_to_dict(node, registry, _checks_for(session, node))


class NodePatch(BaseModel):
    name: str | None = None
    approve: bool | None = None
    labels: dict[str, str] | None = None


@router.patch("/nodes/{uuid}")
def patch_node(
    uuid: str, patch: NodePatch, request: Request, session: Session = Depends(get_session)
) -> dict:
    node = _get_node(session, uuid)
    if patch.name is not None:
        node.name = patch.name
    if patch.labels is not None:
        node.labels_json = json.dumps(patch.labels)
    if patch.approve and node.status == "pending":
        node.approved_at = now_ts()
        node.status = "offline"  # becomes online when the agent reconnects
    session.flush()
    registry: AgentRegistry = request.app.state.agent_registry
    return node_to_dict(node, registry)


@router.get("/nodes/{uuid}/fs")
def node_fs(uuid: str, session: Session = Depends(get_session)) -> list[dict]:
    from app.ingest.handlers import serialize_mount
    from app.models import FsMount

    node = _get_node(session, uuid)
    mounts = session.scalars(
        select(FsMount).where(FsMount.node_id == node.id).order_by(FsMount.mountpoint)
    ).all()
    return [serialize_mount(m) for m in mounts]


@router.delete("/nodes/{uuid}", status_code=204)
def delete_node(uuid: str, session: Session = Depends(get_session)) -> None:
    session.delete(_get_node(session, uuid))
