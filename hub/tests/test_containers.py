import json
import time

from tests.conftest import agent_headers, hello_frame


def containers_full_frame(seq: int, containers: list[dict]) -> str:
    return json.dumps(
        {"t": "containers_full", "seq": seq, "ts": int(time.time()), "containers": containers}
    )


ROMM = {
    "container_id": "abc123",
    "name": "romm",
    "image": "ghcr.io/rommapp/romm:4.6",
    "state": "running",
    "health": "healthy",
    "ports": ["8085:8080/tcp"],
    "labels": {
        "bifrost.url": "https://romm.example",
        "bifrost.group": "media",
        "bifrost.hide": "false",
    },
    "started_at": 1700000000,
}

PIHOLE = {
    "container_id": "def456",
    "name": "pihole",
    "image": "pihole/pihole",
    "state": "exited",
    "health": "",
    "ports": [],
    "labels": {"bifrost.hide": "true"},
    "started_at": 0,
}


def wait_for(cond, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = cond()
        if result:
            return result
        time.sleep(0.03)
    raise AssertionError("condition not met")


def test_containers_full_reconciles(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]

        ws.send_text(containers_full_frame(1, [ROMM, PIHOLE]))
        containers = wait_for(
            lambda: client.get("/api/v1/containers").json() or None
        )
        assert len(containers) == 2
        romm = next(c for c in containers if c["name"] == "romm")
        assert romm["state"] == "running"
        assert romm["health"] == "healthy"
        assert romm["meta"] == {"url": "https://romm.example", "group": "media", "hide": False}
        assert romm["node_uuid"] == node_uuid
        pihole = next(c for c in containers if c["name"] == "pihole")
        assert pihole["meta"]["hide"] is True

        # Next full without pihole → row deleted; romm state updated.
        stopped = dict(ROMM, state="exited", health="")
        ws.send_text(containers_full_frame(2, [stopped]))
        containers = wait_for(
            lambda: (
                lambda cs: cs if len(cs) == 1 and cs[0]["state"] == "exited" else None
            )(client.get("/api/v1/containers").json())
        )
        assert containers[0]["name"] == "romm"


def test_container_event_recorded_and_snapshot_grouped(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]

        ws.send_text(containers_full_frame(1, [ROMM]))
        ws.send_text(
            json.dumps(
                {
                    "t": "container_event",
                    "seq": 2,
                    "ts": int(time.time()),
                    "action": "die",
                    "container": {"container_id": "abc123", "name": "romm", "image": "x"},
                }
            )
        )

        events = wait_for(
            lambda: client.get("/api/v1/events", params={"kind": "container.event"}).json() or None
        )
        assert events[0]["payload"]["action"] == "die"
        assert events[0]["payload"]["name"] == "romm"

        snap = client.get("/api/v1/snapshot").json()
        assert node_uuid in snap["containers"]
        assert snap["containers"][node_uuid][0]["name"] == "romm"


def test_containers_filter_by_node(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]
        ws.send_text(containers_full_frame(1, [ROMM]))
        wait_for(lambda: client.get("/api/v1/containers").json() or None)

    assert client.get("/api/v1/containers", params={"node": node_uuid}).json()[0]["name"] == "romm"
    assert client.get("/api/v1/containers", params={"node": "nope"}).json() == []
