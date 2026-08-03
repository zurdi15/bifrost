import asyncio

import httpx

from app.bus import EventBus
from app.checks import services


def route(host: str, port: int, container: str) -> dict:
    return {
        "host": host, "node": "n", "port": port, "container": container,
        "source": "derived", "hide": False,
    }


ROUTE_OK = route("ok.lab", 1, "a")
ROUTE_DOWN = route("down.lab", 2, "b")


def test_sweep_records_and_publishes_transitions(client, monkeypatch):
    monkeypatch.setattr("app.api.gateway._diagnose", lambda s, d: ([ROUTE_OK, ROUTE_DOWN], []))
    behavior = {"down.lab": 502}

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(behavior.get(request.url.host, 200))

    monkeypatch.setattr(services, "transport", httpx.MockTransport(responder))
    services.results.clear()
    bus = EventBus()
    queue = bus.subscribe()

    asyncio.run(services.sweep_once(bus))
    assert services.results["ok.lab"]["ok"] is True
    assert services.results["ok.lab"]["status"] == 200
    assert services.results["down.lab"]["ok"] is False
    # First sight is baseline, not a transition — silence.
    assert queue.qsize() == 0

    # The broken one recovers → exactly one transition event.
    behavior.pop("down.lab")
    asyncio.run(services.sweep_once(bus))
    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert event.topic == "endpoint.status"
    assert event.data == {"host": "down.lab", "ok": True, "status": 200, "kind": "service"}

    # The report carries the latest result per route.
    report = client.get("/api/v1/gateway/report").json()
    checks = {r["host"]: r["check"] for r in report["routes"]}
    assert checks["down.lab"]["ok"] is True

    services.results.clear()
