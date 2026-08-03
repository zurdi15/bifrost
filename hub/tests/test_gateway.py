import json

from app.config import settings
from app.db import session_scope
from app.models import K8sCluster, K8sIngress
from tests.conftest import agent_headers, hello_frame
from tests.test_containers import containers_full_frame, wait_for


def container(name: str, ports: list[str], labels: dict[str, str]) -> dict:
    return {
        "container_id": f"id-{name}",
        "name": name,
        "image": f"{name}/latest",
        "state": "running",
        "health": "",
        "ports": ports,
        "labels": labels,
        "started_at": 1700000000,
    }

ROMM = {
    "container_id": "abc123",
    "name": "romm",
    "image": "ghcr.io/rommapp/romm:4.6",
    "state": "running",
    "health": "healthy",
    "ports": ["8085:8080/tcp"],
    "labels": {"bifrost.url": "https://romm.lab.example"},
    "started_at": 1700000000,
}

# bifrost.port picks the routable port when several are published.
GRAFANA = {
    "container_id": "def456",
    "name": "grafana",
    "image": "grafana/grafana",
    "state": "running",
    "health": "",
    "ports": ["9094:9094/tcp", "3000:3000/tcp"],
    "labels": {"bifrost.url": "https://grafana.lab.example", "bifrost.port": "3000"},
    "started_at": 1700000000,
}

# A URL but no host-published port: nothing for a gateway to dial.
UNPUBLISHED = {
    "container_id": "ghi789",
    "name": "internal",
    "image": "internal/tool",
    "state": "running",
    "health": "",
    "ports": ["2019/tcp"],
    "labels": {"bifrost.url": "https://internal.lab.example"},
    "started_at": 1700000000,
}

# No bifrost.url at all → not a routed service.
AGENT = {
    "container_id": "jkl012",
    "name": "bifrost-agent",
    "image": "bifrost-agent",
    "state": "running",
    "health": "",
    "ports": [],
    "labels": {},
    "started_at": 1700000000,
}

OTHER_DOMAIN = {
    "container_id": "mno345",
    "name": "blog",
    "image": "nginx",
    "state": "running",
    "health": "",
    "ports": ["8081:80/tcp"],
    "labels": {"bifrost.url": "https://blog.other.example"},
    "started_at": 1700000000,
}


def test_gateway_routes(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]
        ws.send_text(
            containers_full_frame(1, [ROMM, GRAFANA, UNPUBLISHED, AGENT, OTHER_DOMAIN])
        )
        wait_for(lambda: client.get("/api/v1/gateway/routes").json() or None)

        routes = client.get("/api/v1/gateway/routes").json()
        assert routes == [
            {"host": "blog.other.example", "node": "testnode", "port": 8081, "container": "blog"},
            {"host": "grafana.lab.example", "node": "testnode", "port": 3000, "container": "grafana"},
            {"host": "romm.lab.example", "node": "testnode", "port": 8085, "container": "romm"},
        ]

        filtered = client.get("/api/v1/gateway/routes?domain=lab.example").json()
        assert [r["host"] for r in filtered] == ["grafana.lab.example", "romm.lab.example"]

        # A UI override on the URL feeds the gateway too.
        client.put(
            f"/api/v1/containers/{node_uuid}/romm/meta",
            json={"url": "https://games.lab.example"},
        )
        routes = client.get("/api/v1/gateway/routes?domain=lab.example").json()
        assert [r["host"] for r in routes] == ["games.lab.example", "grafana.lab.example"]


def test_gateway_derived_routes(client, monkeypatch):
    monkeypatch.setattr(settings, "service_domain", "lab.example")
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        json.loads(ws.receive_text())
        ws.send_text(
            containers_full_frame(
                1,
                [
                    # single published port, zero labels → derived
                    container("jelly", ["8096:8096/tcp"], {}),
                    # two published ports, no hint → ambiguous, skipped
                    container("torrent", ["9091:9091/tcp", "51413:51413/tcp"], {}),
                    # bifrost.port resolves the ambiguity → derived
                    container("minio", ["9000:9000/tcp", "9001:9001/tcp"], {"bifrost.port": "9001"}),
                    # opted out
                    container("private", ["8080:80/tcp"], {"bifrost.expose": "false"}),
                    # explicit URL still wins over the convention name
                    container("named", ["7000:80/tcp"], {"bifrost.url": "https://pretty.lab.example"}),
                ],
            )
        )
        wait_for(lambda: client.get("/api/v1/gateway/routes").json() or None)

        routes = client.get("/api/v1/gateway/routes").json()
        assert routes == [
            {"host": "jelly.lab.example", "node": "testnode", "port": 8096, "container": "jelly"},
            {"host": "minio.lab.example", "node": "testnode", "port": 9001, "container": "minio"},
            {"host": "pretty.lab.example", "node": "testnode", "port": 7000, "container": "named"},
        ]

        # The card shows the same derived URL the gateway routes.
        cards = {c["name"]: c["meta"] for c in client.get("/api/v1/containers").json()}
        assert cards["jelly"]["url"] == "https://jelly.lab.example"
        assert "url" not in cards["torrent"]
        assert "url" not in cards["private"]


def test_gateway_derived_yields_to_ingress(client, monkeypatch):
    monkeypatch.setattr(settings, "service_domain", "lab.example")
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        json.loads(ws.receive_text())
        ws.send_text(
            containers_full_frame(
                2,
                [
                    container("jelly", ["8096:8096/tcp"], {}),
                    container("named", ["7000:80/tcp"], {"bifrost.url": "https://romm.lab.example"}),
                ],
            )
        )
        wait_for(lambda: client.get("/api/v1/gateway/routes").json() or None)
        with session_scope() as s:
            cluster = K8sCluster(name="k3s")
            s.add(cluster)
            s.flush()
            # jelly already served by an Ingress; romm too, but explicit wins.
            s.add(
                K8sIngress(
                    cluster_id=cluster.id,
                    namespace="apps",
                    name="media",
                    hosts_json='["jelly.lab.example", "romm.lab.example"]',
                )
            )

        hosts = [r["host"] for r in client.get("/api/v1/gateway/routes").json()]
        assert hosts == ["romm.lab.example"]
