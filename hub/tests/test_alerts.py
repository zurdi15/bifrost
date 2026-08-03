import asyncio
import json
import time

import httpx

from app.alerts import engine as alerts
from app.bus import Event
from tests.conftest import agent_headers, hello_frame  # noqa: F401


def make_event(topic: str, data: dict) -> Event:
    return Event(topic=topic, data=data, seq=1, ts=int(time.time()))


def test_rule_crud_and_validation(client):
    created = client.post(
        "/api/v1/alert-rules",
        json={"name": "down alerts", "kind": "node.status", "notifier": "ntfy",
              "target": "https://ntfy.sh/bifrost-test"},
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["min_severity"] == "warning"

    assert client.post(
        "/api/v1/alert-rules",
        json={"name": "x", "kind": "nope", "notifier": "ntfy", "target": "t"},
    ).status_code == 422
    assert client.post(
        "/api/v1/alert-rules",
        json={"name": "x", "notifier": "carrier-pigeon", "target": "t"},
    ).status_code == 422

    patched = client.patch(f"/api/v1/alert-rules/{rule['id']}", json={"enabled": False}).json()
    assert patched["enabled"] is False
    assert client.delete(f"/api/v1/alert-rules/{rule['id']}").status_code == 204


def test_engine_matches_and_notifies(client, monkeypatch):
    sent: list[httpx.Request] = []

    def capture(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(alerts, "transport", httpx.MockTransport(capture))

    client.post(
        "/api/v1/alert-rules",
        json={"name": "downs", "kind": "node.status", "notifier": "ntfy",
              "target": "https://ntfy.sh/topic", "cooldown_s": 60},
    )
    client.post(
        "/api/v1/alert-rules",
        json={"name": "everything", "kind": "*", "min_severity": "info",
              "notifier": "webhook", "target": "https://hooks.example/x"},
    )

    engine = alerts.AlertEngine()

    async def scenario():
        # Warning node.status matches both rules.
        await engine.handle(make_event("node.status", {"uuid": "abc123", "status": "offline"}))
        assert len(sent) == 2
        ntfy = next(r for r in sent if "ntfy.sh" in str(r.url))
        assert "DOWN" in ntfy.headers["Title"].upper() or "OFFLINE" in ntfy.headers["Title"].upper()
        webhook = next(r for r in sent if "hooks.example" in str(r.url))
        payload = json.loads(webhook.content)
        assert payload["severity"] == "warning"

        # Cooldown suppresses an immediate repeat for the same subject on
        # both rules — nothing new goes out.
        await engine.handle(make_event("node.status", {"uuid": "abc123", "status": "offline"}))
        assert len(sent) == 2

        # A different subject is not affected by the cooldown.
        await engine.handle(make_event("node.status", {"uuid": "otro", "status": "offline"}))
        assert len(sent) == 4
    asyncio.run(scenario())


def test_engine_severity_filter(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        alerts, "transport",
        httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(200))[1]),
    )
    client.post(
        "/api/v1/alert-rules",
        json={"name": "warnings only", "kind": "*", "notifier": "webhook",
              "target": "https://hooks.example/w"},
    )
    engine = alerts.AlertEngine()

    async def scenario():
        # info-level event → filtered out by min_severity=warning.
        await engine.handle(make_event("node.status", {"uuid": "n", "status": "online"}))
        assert sent == []
        # failed cronjob → warning → delivered.
        await engine.handle(
            make_event("k8s.cronjob.run", {"cronjob": "backup", "succeeded": False,
                                           "failure_reason": "disk full"})
        )
        assert len(sent) == 1
        payload = json.loads(sent[0].content)
        assert "backup" in payload["title"]
        assert payload["body"] == "disk full"

    asyncio.run(scenario())


def test_cooldown_on_freshly_booted_host(client, monkeypatch):
    """Regression: time.monotonic() is seconds since boot on Linux. Right
    after boot its value is smaller than the cooldown window, and a 0.0
    'never sent' sentinel made the engine mute every alert until uptime
    exceeded cooldown_s. Caught by CI runners, which always boot fresh."""
    sent = []
    monkeypatch.setattr(
        alerts, "transport",
        httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(200))[1]),
    )
    # 40s of uptime, rule cooldown 300s.
    monkeypatch.setattr(alerts.time, "monotonic", lambda: 40.0)
    client.post(
        "/api/v1/alert-rules",
        json={"name": "boot", "kind": "node.status", "notifier": "webhook",
              "target": "https://hooks.example/boot", "cooldown_s": 300},
    )
    engine = alerts.AlertEngine()

    async def scenario():
        await engine.handle(make_event("node.status", {"uuid": "n1", "status": "offline"}))
        assert len(sent) == 1  # first-ever alert must never be suppressed

    asyncio.run(scenario())


def test_rule_test_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        alerts, "transport", httpx.MockTransport(lambda r: httpx.Response(200))
    )
    rule = client.post(
        "/api/v1/alert-rules",
        json={"name": "t", "notifier": "webhook", "target": "https://hooks.example/t"},
    ).json()
    assert client.post(f"/api/v1/alert-rules/{rule['id']}/test").json() == {"sent": True}

    monkeypatch.setattr(
        alerts, "transport", httpx.MockTransport(lambda r: httpx.Response(500))
    )
    assert client.post(f"/api/v1/alert-rules/{rule['id']}/test").status_code == 502


def test_telegram_notifier(client, monkeypatch):
    sent: list[httpx.Request] = []

    def capture(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(alerts, "transport", httpx.MockTransport(capture))
    monkeypatch.setattr(alerts.settings, "telegram_bot_token", "123:ABC")

    client.post(
        "/api/v1/alert-rules",
        json={"name": "tg", "kind": "node.status", "notifier": "telegram",
              "target": "-100555"},
    )
    engine = alerts.AlertEngine()

    async def scenario():
        await engine.handle(
            make_event(
                "node.status", {"uuid": "abc123", "status": "offline", "name": "asgard"}
            )
        )
        assert len(sent) == 1
        request = sent[0]
        assert str(request.url) == "https://api.telegram.org/bot123:ABC/sendMessage"
        payload = json.loads(request.content)
        assert payload["chat_id"] == "-100555"
        assert "asgard" in payload["text"] and "OFFLINE" in payload["text"]

    asyncio.run(scenario())


def test_telegram_rejected_without_token(client):
    response = client.post(
        "/api/v1/alert-rules",
        json={"name": "bad", "kind": "*", "notifier": "smoke", "target": "x"},
    )
    assert response.status_code == 422
