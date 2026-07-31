import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import protocol as proto
from app.models import Container, Disk, FsMount, now_ts

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


def serialize_mount(mount: FsMount) -> dict:
    used_pct = None
    if mount.total_bytes:
        used_pct = round((mount.used_bytes or 0) * 100 / mount.total_bytes, 2)
    return {
        "mountpoint": mount.mountpoint,
        "device": mount.device,
        "fstype": mount.fstype,
        "total_bytes": mount.total_bytes,
        "used_bytes": mount.used_bytes,
        "used_pct": used_pct,
        "stale": mount.stale,
        "updated_at": mount.updated_at,
    }


def serialize_disk(disk: Disk, node_uuid: str = "", node_name: str = "") -> dict:
    return {
        "device": disk.device,
        "model": disk.model,
        "serial": disk.serial,
        "kind": disk.kind,
        "capacity_bytes": disk.capacity_bytes,
        "smart_status": disk.smart_status,
        "temp_c": disk.temp_c,
        "power_on_hours": disk.power_on_hours,
        "realloc_sectors": disk.realloc_sectors,
        "pending_sectors": disk.pending_sectors,
        "wear_pct": disk.wear_pct,
        "updated_at": disk.updated_at,
        "node_uuid": node_uuid,
        "node_name": node_name,
    }


def apply_smart(session: Session, node_id: int, disks: list[proto.SmartDisk]) -> list[Disk]:
    """Upsert the node's disk set by serial; returns current rows."""
    existing = {
        d.serial: d for d in session.scalars(select(Disk).where(Disk.node_id == node_id))
    }
    seen: set[str] = set()
    ts = now_ts()
    for info in disks:
        serial = info.serial or info.device  # some USB bridges hide serials
        seen.add(serial)
        row = existing.get(serial)
        if row is None:
            row = Disk(node_id=node_id, serial=serial, device=info.device)
            session.add(row)
        row.device = info.device
        row.model = info.model
        row.kind = info.kind
        row.capacity_bytes = info.capacity_bytes
        row.smart_status = info.smart_status
        row.temp_c = info.temp_c
        row.power_on_hours = info.power_on_hours
        row.realloc_sectors = info.realloc_sectors
        row.pending_sectors = info.pending_sectors
        row.wear_pct = info.wear_pct
        row.smart_json = info.raw_json
        row.updated_at = ts
    for serial, row in existing.items():
        if serial not in seen:
            session.delete(row)
    session.flush()
    return list(
        session.scalars(select(Disk).where(Disk.node_id == node_id).order_by(Disk.device))
    )


def apply_fs(session: Session, node_id: int, mounts: list[proto.FsMountInfo]) -> list[dict]:
    """Reconcile the node's mount snapshot; returns the serialized list."""
    existing = {
        m.mountpoint: m
        for m in session.scalars(select(FsMount).where(FsMount.node_id == node_id))
    }
    seen: set[str] = set()
    ts = now_ts()
    for info in mounts:
        seen.add(info.mountpoint)
        row = existing.get(info.mountpoint)
        if row is None:
            row = FsMount(node_id=node_id, mountpoint=info.mountpoint)
            session.add(row)
        row.device = info.device
        row.fstype = info.fstype
        row.total_bytes = info.total_bytes
        row.used_bytes = info.used_bytes
        row.stale = info.stale
        row.updated_at = ts
    for mountpoint, row in existing.items():
        if mountpoint not in seen:
            session.delete(row)
    session.flush()
    rows = session.scalars(
        select(FsMount).where(FsMount.node_id == node_id).order_by(FsMount.mountpoint)
    ).all()
    return [serialize_mount(m) for m in rows]
