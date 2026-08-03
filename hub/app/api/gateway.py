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

from app.config import settings
from app.db import get_session
from app.ingest.handlers import derive_url, merge_override, published_tcp_ports
from app.models import Container, K8sIngress, Node, ServiceOverride

router = APIRouter()


@router.get("/gateway/routes")
def gateway_routes(
    session: Session = Depends(get_session), domain: str | None = None
) -> list[dict]:
    """Routes for every container with an explicit bifrost.url plus, when
    service_domain is set, derived ones for label-less containers with an
    unambiguous port. Derived hostnames yield to k8s Ingresses already serving
    them (explicit URLs are deliberate and win). `domain` keeps only hostnames
    equal to or under it. First one wins on duplicate hostnames (rows come
    ordered by node and container name)."""
    rows = session.execute(
        select(Container, Node)
        .join(Node, Container.node_id == Node.id)
        .order_by(Node.name, Container.name)
    ).all()
    overrides = {
        (o.node_id, o.container_name): o for o in session.scalars(select(ServiceOverride))
    }
    ingress_hosts: set[str] = set()
    for hosts_json in session.scalars(select(K8sIngress.hosts_json)):
        ingress_hosts.update(json.loads(hosts_json or "[]"))

    routes: dict[str, dict] = {}
    for container, node in rows:
        meta = merge_override(
            json.loads(container.bifrost_meta_json or "{}"),
            overrides.get((container.node_id, container.name)),
        )
        explicit = meta.get("url")
        url = explicit or derive_url(container, meta, settings.service_domain)
        host = urlparse(url or "").hostname
        if not host:
            continue
        if not explicit and host in ingress_hosts:
            continue
        if domain and host != domain and not host.endswith("." + domain):
            continue
        published = published_tcp_ports(json.loads(container.ports_json or "[]"))
        port = meta.get("port") or (published[0] if published else None)
        if port is None or not str(port).isdigit():
            continue
        routes.setdefault(
            host,
            {"host": host, "node": node.name, "port": int(port), "container": container.name},
        )
    return sorted(routes.values(), key=lambda r: r["host"])
