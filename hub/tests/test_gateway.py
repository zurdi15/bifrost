import json

from tests.conftest import agent_headers, hello_frame
from tests.test_containers import containers_full_frame, wait_for

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
