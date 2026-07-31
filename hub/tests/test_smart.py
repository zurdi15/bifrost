import json
import time

from tests.conftest import agent_headers, hello_frame
from tests.test_containers import wait_for


def smart_frame(seq: int, disks: list[dict]) -> str:
    return json.dumps({"t": "smart", "seq": seq, "ts": int(time.time()), "disks": disks})


WD_RED = {
    "device": "/dev/sda",
    "model": "WDC WD80EFAX",
    "serial": "VAG12345",
    "kind": "hdd",
    "capacity_bytes": 8_001_563_222_016,
    "smart_status": "passed",
    "temp_c": 38.0,
    "power_on_hours": 21504,
    "realloc_sectors": 0,
    "pending_sectors": 0,
    "wear_pct": None,
    "raw_json": "{}",
}


def test_smart_upsert_and_rest(client):
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]

        ws.send_text(smart_frame(1, [WD_RED]))
        disks = wait_for(lambda: client.get("/api/v1/disks").json() or None)
        assert disks[0]["serial"] == "VAG12345"
        assert disks[0]["smart_status"] == "passed"
        assert disks[0]["temp_c"] == 38.0
        assert disks[0]["node_uuid"] == node_uuid

        # Same serial → update, not duplicate; temperature history recorded.
        hot = dict(WD_RED, temp_c=44.0, smart_status="failed")
        ws.send_text(smart_frame(2, [hot]))
        disks = wait_for(
            lambda: (
                lambda ds: ds if ds and ds[0]["temp_c"] == 44.0 else None
            )(client.get("/api/v1/disks").json())
        )
        assert len(disks) == 1
        assert disks[0]["smart_status"] == "failed"

        snap = client.get("/api/v1/snapshot").json()
        assert snap["disks"][node_uuid][0]["serial"] == "VAG12345"

    # Failed SMART surfaces as a warning in the timeline.
    events = client.get("/api/v1/events", params={"kind": "disk.updated"}).json()
    assert any(e["severity"] == "warning" for e in events)


def test_disk_temp_metric_recorded(client):
    now = int(time.time())
    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        node_uuid = json.loads(ws.receive_text())["node_uuid"]
        ws.send_text(smart_frame(1, [WD_RED]))

        def query():
            series = client.get(
                "/api/v1/metrics",
                params={
                    "node": node_uuid,
                    "m": "disk.VAG12345.temp",
                    "from": now - 60,
                    "to": now + 60,
                    "res": "raw",
                },
            ).json()["series"]["disk.VAG12345.temp"]
            return series or None

        # Generous deadline: the flush cadence is 0.05s in tests, but starved
        # CI runners have blown through 3s before.
        series = wait_for(query, timeout=10.0)
        assert series[0][1] == 38.0
