from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.ingest.handlers import serialize_disk
from app.models import Disk, Node

router = APIRouter()


@router.get("/disks")
def list_disks(session: Session = Depends(get_session), node: str | None = None) -> list[dict]:
    stmt = select(Disk, Node).join(Node, Disk.node_id == Node.id).order_by(Node.name, Disk.device)
    if node is not None:
        stmt = stmt.where(Node.uuid == node)
    return [serialize_disk(d, n.uuid, n.name) for d, n in session.execute(stmt).all()]


def disks_by_node(session: Session) -> dict[str, list[dict]]:
    stmt = select(Disk, Node).join(Node, Disk.node_id == Node.id).order_by(Disk.device)
    grouped: dict[str, list[dict]] = {}
    for disk, node in session.execute(stmt).all():
        grouped.setdefault(node.uuid, []).append(serialize_disk(disk, node.uuid, node.name))
    return grouped
