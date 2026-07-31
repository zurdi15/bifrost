
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.ingest.handlers import serialize_container
from app.models import Container, Node

router = APIRouter()


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
    return [serialize_container(c, n.uuid, n.name) for c, n in session.execute(stmt).all()]


def containers_by_node(session: Session) -> dict[str, list[dict]]:
    """uuid → containers, for the snapshot payload."""
    stmt = select(Container, Node).join(Node, Container.node_id == Node.id).order_by(Container.name)
    grouped: dict[str, list[dict]] = {}
    for container, node in session.execute(stmt).all():
        grouped.setdefault(node.uuid, []).append(
            serialize_container(container, node.uuid, node.name)
        )
    return grouped
