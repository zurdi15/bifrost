"""Gateway route feed: hostname → node:port for Docker services.

The k8s side of a homelab is self-routing (Ingress → the gateway's wildcard →
the cluster's ingress controller), but Docker containers have no equivalent:
a bifrost.url label only decorates the dashboard card. This endpoint closes
that gap — a reverse proxy fronting the homelab can poll it and render one
vhost per container that advertises a URL and a routable port (the
bifrost.port label, or its first host-published TCP port)."""

import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.ingest.handlers import merge_override
from app.models import Container, Node, ServiceOverride

router = APIRouter()


def _published_port(ports: list[str]) -> int | None:
    """First host-published TCP port: "8085:8080/tcp" → 8085. Tolerates a bind
    address prefix ("0.0.0.0:8085:8080"); "2019/tcp" alone is unpublished."""
    for entry in ports:
        spec, _, proto = entry.partition("/")
        if proto not in ("", "tcp"):
            continue
        parts = spec.split(":")
        if len(parts) >= 2 and parts[-2].isdigit():
            return int(parts[-2])
    return None


@router.get("/gateway/routes")
def gateway_routes(
    session: Session = Depends(get_session), domain: str | None = None
) -> list[dict]:
    """Routes for every container whose merged meta carries a URL. `domain`
    keeps only hostnames equal to or under it. First one wins on duplicate
    hostnames (rows come ordered by node and container name)."""
    rows = session.execute(
        select(Container, Node)
        .join(Node, Container.node_id == Node.id)
        .order_by(Node.name, Container.name)
    ).all()
    overrides = {
        (o.node_id, o.container_name): o for o in session.scalars(select(ServiceOverride))
    }
    routes: dict[str, dict] = {}
    for container, node in rows:
        meta = merge_override(
            json.loads(container.bifrost_meta_json or "{}"),
            overrides.get((container.node_id, container.name)),
        )
        host = urlparse(meta.get("url") or "").hostname
        if not host:
            continue
        if domain and host != domain and not host.endswith("." + domain):
            continue
        port = meta.get("port") or _published_port(json.loads(container.ports_json or "[]"))
        if port is None or not str(port).isdigit():
            continue
        routes.setdefault(
            host,
            {"host": host, "node": node.name, "port": int(port), "container": container.name},
        )
    return sorted(routes.values(), key=lambda r: r["host"])
