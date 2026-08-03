
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.ingest.handlers import collapse_override, list_node_containers, serialize_container
from app.models import Container, Node, ServiceOverride

router = APIRouter()


def _overrides(session: Session) -> dict[tuple[int, str], ServiceOverride]:
    return {
        (o.node_id, o.container_name): o for o in session.scalars(select(ServiceOverride))
    }


@router.get("/containers")
def list_containers(
    session: Session = Depends(get_session), node: str | None = None
) -> list[dict]:
    stmt = (
        select(Container, Node)
        .join(Node, Container.node_id == Node.id)
        .order_by(Node.name, Container.name)
    )
    if node is not None:
        stmt = stmt.where(Node.uuid == node)
    overrides = _overrides(session)
    return [
        serialize_container(c, n.uuid, n.name, overrides.get((c.node_id, c.name)))
        for c, n in session.execute(stmt).all()
    ]


def containers_by_node(session: Session) -> dict[str, list[dict]]:
    """uuid → containers, for the snapshot payload."""
    stmt = select(Container, Node).join(Node, Container.node_id == Node.id).order_by(Container.name)
    overrides = _overrides(session)
    grouped: dict[str, list[dict]] = {}
    for container, node in session.execute(stmt).all():
        grouped.setdefault(node.uuid, []).append(
            serialize_container(
                container, node.uuid, node.name, overrides.get((container.node_id, container.name))
            )
        )
    return grouped


class ServiceMetaPut(BaseModel):
    name: str | None = None
    icon: str | None = None
    url: str | None = None
    group: str | None = None
    hide: bool | None = None


@router.put("/containers/{node_uuid}/{container_name}/meta")
def put_container_meta(
    node_uuid: str,
    container_name: str,
    body: ServiceMetaPut,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Full replace of the UI overrides for one service. Empty/absent fields
    fall back to the bifrost.* labels, and so do fields that merely repeat
    them; an all-empty body removes the row."""
    node = session.scalar(select(Node).where(Node.uuid == node_uuid))
    if node is None:
        raise HTTPException(404)
    override = session.scalar(
        select(ServiceOverride).where(
            ServiceOverride.node_id == node.id,
            ServiceOverride.container_name == container_name,
        )
    )
    container = session.scalar(
        select(Container).where(
            Container.node_id == node.id, Container.name == container_name
        )
    )
    label_meta = json.loads(container.bifrost_meta_json or "{}") if container else {}
    values = collapse_override(
        {
            "name": (body.name or "").strip() or None,
            "icon": (body.icon or "").strip() or None,
            "url": (body.url or "").strip() or None,
            "group_name": (body.group or "").strip() or None,
            "hide": body.hide,
        },
        label_meta,
    )
    if all(v is None for v in values.values()):
        if override is not None:
            session.delete(override)
    else:
        if override is None:
            override = ServiceOverride(node_id=node.id, container_name=container_name)
            session.add(override)
        for field, value in values.items():
            setattr(override, field, value)
    session.flush()

    serialized = list_node_containers(session, node.id, node.uuid, node.name)
    request.app.state.bus.publish(
        "containers.updated", {"uuid": node.uuid, "containers": serialized}
    )
    updated = next((c for c in serialized if c["name"] == container_name), None)
    return updated or {"name": container_name, "meta": {}}
