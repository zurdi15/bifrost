"""Auto-registration of clusters reported by agents via k8s_detected."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import protocol as proto
from app.k8s.client import K8sAuthError, parse_kubeconfig, rewrite_localhost
from app.models import K8sCluster, Node

logger = logging.getLogger("bifrost.k8s")


def register_discovered_cluster(
    session: Session, node: Node, msg: proto.K8sDetected, node_address: str
) -> tuple[K8sCluster, bool]:
    """Create or refresh the cluster detected on a node. Returns (row, created).

    With a readable kubeconfig the cluster is immediately operational: a
    localhost API server URL is rewritten to the address the agent connected
    from. Without one, the row waits for credentials from the UI."""
    name = f"{msg.distro or 'k8s'}@{node.name}"
    cluster = session.scalar(
        select(K8sCluster).where(
            K8sCluster.source == "discovered", K8sCluster.discovered_node_id == node.id
        )
    )
    created = cluster is None
    if cluster is None:
        cluster = K8sCluster(
            name=name, source="discovered", discovered_node_id=node.id, enabled=True
        )
        session.add(cluster)
    else:
        # Discovered names follow the node (it may have healed from a
        # container-id hostname to the real one since first contact).
        cluster.name = name

    api_url = msg.api_endpoint
    if msg.kubeconfig:
        try:
            parsed = parse_kubeconfig(msg.kubeconfig)
            api_url = rewrite_localhost(parsed["server"] or api_url, node_address)
            cluster.kubeconfig_content = msg.kubeconfig
            cluster.auth_mode = "kubeconfig"
            cluster.status = cluster.status or "discovered"
        except K8sAuthError as exc:
            logger.warning("discovered kubeconfig from %s unparseable: %s", node.name, exc)
    if api_url:
        cluster.api_url = rewrite_localhost(api_url, node_address)
    session.flush()
    return cluster, created
