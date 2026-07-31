import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import protocol as proto
from app.models import Container, now_ts

BIFROST_LABEL_PREFIX = "bifrost."
META_KEYS = ("icon", "url", "group", "hide")


def extract_bifrost_meta(labels: dict[str, str]) -> dict:
    """bifrost.* labels → widget metadata. `hide` is boolean, rest are strings."""
    meta: dict = {}
    for key in META_KEYS:
        value = labels.get(BIFROST_LABEL_PREFIX + key)
        if value is None:
            continue
        meta[key] = value.lower() in ("true", "1", "yes") if key == "hide" else value
    return meta


def serialize_container(container: Container, node_uuid: str, node_name: str) -> dict:
    return {
        "id": container.container_id,
        "name": container.name,
        "image": container.image,
        "state": container.state,
        "health": container.health,
        "ports": json.loads(container.ports_json or "[]"),
        "meta": json.loads(container.bifrost_meta_json or "{}"),
        "started_at": container.started_at,
        "updated_at": container.updated_at,
        "node_uuid": node_uuid,
        "node_name": node_name,
    }


def apply_containers_full(
    session: Session, node_id: int, containers: list[proto.ContainerInfo]
) -> None:
    """Reconcile the node's container set: upsert reported, delete vanished."""
    existing = {
        c.container_id: c
        for c in session.scalars(select(Container).where(Container.node_id == node_id))
    }
    seen: set[str] = set()
    ts = now_ts()
    for info in containers:
        seen.add(info.container_id)
        row = existing.get(info.container_id)
        if row is None:
            row = Container(node_id=node_id, container_id=info.container_id, name=info.name)
            session.add(row)
        row.name = info.name
        row.image = info.image
        row.state = info.state
        row.health = info.health
        row.ports_json = json.dumps(info.ports)
        row.labels_json = json.dumps(info.labels)
        row.bifrost_meta_json = json.dumps(extract_bifrost_meta(info.labels))
        row.started_at = info.started_at
        row.updated_at = ts
    for container_id, row in existing.items():
        if container_id not in seen:
            session.delete(row)


def list_node_containers(
    session: Session, node_id: int, node_uuid: str, node_name: str
) -> list[dict]:
    rows = session.scalars(
        select(Container).where(Container.node_id == node_id).order_by(Container.name)
    ).all()
    return [serialize_container(c, node_uuid, node_name) for c in rows]
