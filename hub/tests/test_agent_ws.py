import json
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import agent_headers, hello_frame, metrics_frame


def test_enroll_and_hello_ack(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        ack = json.loads(ws.receive_text())
        assert ack["t"] == "hello_ack"
        assert ack["agent_token"]  # minted on enrollment
        assert ack["resume_from_seq"] == 0

        nodes = client.get("/api/v1/nodes").json()
        assert len(nodes) == 1
        assert nodes[0]["status"] == "online"
        assert nodes[0]["name"] == "testnode"
        assert nodes[0]["uuid"] == ack["node_uuid"]


def test_name_follows_hostname_until_renamed(client):
    """Regression: agents running in Docker used to report the container id
    as hostname. Once the agent reports the real host hostname, the node name
    must heal — but an explicit user rename always wins."""
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame(hostname="745247e22129"))
        ws.receive_text()

    # Fixed agent reconnects with the real hostname → name follows.
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame(hostname="gateway"))
        ws.receive_text()
        node = client.get("/api/v1/nodes").json()[0]
        assert node["name"] == "gateway"

    # Explicit rename: future hostname changes no longer touch the name.
    client.patch(f"/api/v1/nodes/{node['uuid']}", json={"name": "puerta"})
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame(hostname="gateway-2"))
        ws.receive_text()
        assert client.get("/api/v1/nodes").json()[0]["name"] == "puerta"


def test_wrong_token_rejected(client):
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(
        "/api/ws/agent", headers=agent_headers(token="wrong")
    ) as ws:
        ws.send_text(hello_frame())
        ws.receive_text()


def test_per_agent_token_reconnect(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        token = json.loads(ws.receive_text())["agent_token"]

    with client.websocket_connect("/api/ws/agent", headers=agent_headers(token=token)) as ws:
        ws.send_text(hello_frame())
        ack = json.loads(ws.receive_text())
        assert ack["t"] == "hello_ack"
        assert ack["agent_token"] is None  # not enrolling: no new token minted


def test_offline_on_disconnect(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        ws.receive_text()

    deadline = time.time() + 2
    while time.time() < deadline:
        nodes = client.get("/api/v1/nodes").json()
        if nodes[0]["status"] == "offline":
            break
        time.sleep(0.02)
    assert nodes[0]["status"] == "offline"

    events = client.get("/api/v1/events", params={"kind": "node.status"}).json()
    statuses = [e["payload"]["status"] for e in events]
    assert "offline" in statuses


def test_metrics_ingest_and_query(client):
    now = int(time.time())
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        ack = json.loads(ws.receive_text())
        node_uuid = ack["node_uuid"]

        ws.send_text(metrics_frame(1, now - 10, {"cpu.pct": 12.5, "mem.used": 1024.0}))
        ws.send_text(metrics_frame(2, now, {"cpu.pct": 50.0, "mem.used": 2048.0}))

        # Live snapshot appears on the node without touching metrics.db.
        deadline = time.time() + 2
        while time.time() < deadline:
            node = client.get(f"/api/v1/nodes/{node_uuid}").json()
            if node["live"] and node["live"]["samples"].get("cpu.pct") == 50.0:
                break
            time.sleep(0.02)
        assert node["live"]["samples"]["cpu.pct"] == 50.0

        # Batched writer lands both rows (fast flush interval from conftest).
        deadline = time.time() + 3
        series = {}
        while time.time() < deadline:
            series = client.get(
                "/api/v1/metrics",
                params={"node": node_uuid, "m": "cpu.pct", "from": now - 60, "to": now + 60},
            ).json()["series"]
            if len(series.get("cpu.pct", [])) == 2:
                break
            time.sleep(0.05)
        assert [v for _, v in series["cpu.pct"]] == [12.5, 50.0]


def test_duplicate_seq_ignored(client):
    now = int(time.time())
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]

        ws.send_text(metrics_frame(1, now, {"cpu.pct": 10.0}))
        ws.send_text(metrics_frame(1, now + 1, {"cpu.pct": 99.0}))  # replayed seq

        deadline = time.time() + 3
        while time.time() < deadline:
            series = client.get(
                "/api/v1/metrics",
                params={"node": node_uuid, "m": "cpu.pct", "from": now - 60, "to": now + 60},
            ).json()["series"]
            if series.get("cpu.pct"):
                break
            time.sleep(0.05)
        assert [v for _, v in series["cpu.pct"]] == [10.0]


def test_restarted_agent_resets_seq_position(client):
    """A stateless agent restart resets seq to 0; the hub must follow the
    hello's start_seq instead of dropping every new frame as a duplicate."""
    now = int(time.time())
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]
        for seq in range(1, 15):
            ws.send_text(metrics_frame(seq, now - 100 + seq, {"cpu.pct": float(seq)}))
        # >= ACK_EVERY messages force a last_seq persist before disconnect.
        deadline = time.time() + 2
        while time.time() < deadline:
            if json.loads(ws.receive_text())["t"] == "ack":
                break

    # Restarted process: hello declares start_seq 0 (default in hello_frame).
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        ack = json.loads(ws.receive_text())
        assert ack["resume_from_seq"] == 0

        ws.send_text(metrics_frame(1, now + 10, {"cpu.pct": 77.0}))
        deadline = time.time() + 3
        found = False
        while time.time() < deadline and not found:
            series = client.get(
                "/api/v1/metrics",
                params={"node": node_uuid, "m": "cpu.pct", "from": now, "to": now + 60},
            ).json()["series"]["cpu.pct"]
            found = any(v == 77.0 for _, v in series)
            time.sleep(0.05)
        assert found, "fresh-process frame was dropped as duplicate"


def test_pending_approval_flow(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "auto_approve", False)

    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        msg = json.loads(ws.receive_text())
        assert msg["t"] == "error"
        assert msg["code"] == "pending_approval"

    nodes = client.get("/api/v1/nodes").json()
    assert nodes[0]["status"] == "pending"

    client.patch(f"/api/v1/nodes/{nodes[0]['uuid']}", json={"approve": True})

    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        ack = json.loads(ws.receive_text())
        assert ack["t"] == "hello_ack"


def test_rename_and_delete_node(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]

    renamed = client.patch(f"/api/v1/nodes/{node_uuid}", json={"name": "mimir"}).json()
    assert renamed["name"] == "mimir"

    assert client.delete(f"/api/v1/nodes/{node_uuid}").status_code == 204
    assert client.get(f"/api/v1/nodes/{node_uuid}").status_code == 404
