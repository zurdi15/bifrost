import json

from tests.conftest import agent_headers, hello_frame


def test_snapshot_and_status_broadcast(client):
    snapshot = client.get("/api/v1/snapshot").json()
    assert snapshot["nodes"] == []
    base_seq = snapshot["seq"]

    with client.websocket_connect("/api/ws/ui") as ui:
        with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as agent:
            agent.send_text(hello_frame(hostname="freyja"))
            agent.receive_text()

            event = json.loads(ui.receive_text())
            assert event["topic"] == "node.status"
            assert event["data"]["status"] == "online"
            assert event["seq"] > base_seq

        # Agent socket closed → offline broadcast reaches the UI.
        event = json.loads(ui.receive_text())
        assert event["topic"] == "node.status"
        assert event["data"]["status"] == "offline"


def test_ui_ping_returns_current_seq(client):
    with client.websocket_connect("/api/ws/ui") as ui:
        ui.send_text(json.dumps({"ping": True}))
        pong = json.loads(ui.receive_text())
        assert pong["pong"] is True
        assert "seq" in pong


def test_ui_subscription_filter(client):
    with client.websocket_connect("/api/ws/ui") as ui:
        ui.send_text(json.dumps({"sub": ["events"], "ping": True}))
        json.loads(ui.receive_text())  # pong confirms the sub was applied

        with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as agent:
            agent.send_text(hello_frame())
            agent.receive_text()

        # node.status is category 'nodes' — filtered out. Only the pong arrives.
        ui.send_text(json.dumps({"ping": True}))
        msg = json.loads(ui.receive_text())
        assert msg.get("pong") is True
