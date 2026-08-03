"""Gateway route feed: hostname → node:port for Docker services.

The k8s side of a homelab is self-routing (Ingress → the gateway's wildcard →
the cluster's ingress controller), but Docker containers have no equivalent:
a bifrost.url label only decorates the dashboard card. These endpoints close
that gap — /gateway/routes is the machine feed a reverse proxy polls to
render vhosts, and /gateway/report is the same analysis with the excluded
containers and their reasons, for the dashboard's Gateway view."""

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


def _diagnose(session: Session, domain: str | None) -> tuple[list[dict], list[dict]]:
    """(routes, excluded) over every Docker container. Explicit URLs are
    deliberate and win; derived hostnames yield to k8s Ingresses already
    serving them. First one wins on duplicate hostnames (rows come ordered
    by node and container name)."""
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
    excluded: list[dict] = []
    for container, node in rows:
        meta = merge_override(
            json.loads(container.bifrost_meta_json or "{}"),
            overrides.get((container.node_id, container.name)),
        )
        entry = {"container": container.name, "node": node.name}
        explicit = meta.get("url")
        published = published_tcp_ports(json.loads(container.ports_json or "[]"))
        port = meta.get("port") or (published[0] if published else None)
        url = explicit or derive_url(container, meta, settings.service_domain)
        if not url:
            if meta.get("expose") is False:
                excluded.append({**entry, "reason": "opted_out"})
            elif not settings.service_domain:
                excluded.append({**entry, "reason": "no_domain"})
            elif len(published) > 1:
                detail = ", ".join(str(p) for p in published)
                excluded.append({**entry, "reason": "ambiguous_ports", "detail": detail})
            else:
                excluded.append({**entry, "reason": "no_ports"})
            continue
        host = urlparse(url).hostname
        if not host:
            excluded.append({**entry, "reason": "bad_url", "detail": url})
            continue
        if not explicit and host in ingress_hosts:
            excluded.append({**entry, "reason": "ingress_conflict", "detail": host})
            continue
        if domain and host != domain and not host.endswith("." + domain):
            excluded.append({**entry, "reason": "outside_domain", "detail": host})
            continue
        if port is None or not str(port).isdigit():
            excluded.append({**entry, "reason": "no_port", "detail": host})
            continue
        if host in routes:
            excluded.append({**entry, "reason": "duplicate_host", "detail": host})
            continue
        routes[host] = {
            **entry,
            "host": host,
            "port": int(port),
            "source": "explicit" if explicit else "derived",
            "hide": meta.get("hide") is True,
        }
    return sorted(routes.values(), key=lambda r: r["host"]), excluded


@router.get("/gateway/routes")
def gateway_routes(
    session: Session = Depends(get_session), domain: str | None = None
) -> list[dict]:
    """The machine feed: stable four-field shape, consumed by gateway
    renderers (see examples/gateway). `domain` keeps only hostnames equal
    to or under it."""
    routes, _ = _diagnose(session, domain)
    return [
        {"host": r["host"], "node": r["node"], "port": r["port"], "container": r["container"]}
        for r in routes
    ]


@router.get("/gateway/report")
def gateway_report(
    session: Session = Depends(get_session), domain: str | None = None
) -> dict:
    """Routing diagnosis for the dashboard: the routes plus every container
    left out and why."""
    routes, excluded = _diagnose(session, domain)
    return {"domain": settings.service_domain, "routes": routes, "excluded": excluded}
