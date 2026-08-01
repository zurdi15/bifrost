
import httpx

from app.widgets import weather


def test_widget_crud_and_dashboard(client):
    created = client.post(
        "/api/v1/widgets", json={"type": "clock", "config": {"show_seconds": False}}
    )
    assert created.status_code == 201
    widget = created.json()
    assert widget["config"]["show_seconds"] is False

    assert client.post("/api/v1/widgets", json={"type": "nope"}).status_code == 422
    assert (
        client.post("/api/v1/widgets", json={"type": "weather", "config": {"lat": 999, "lon": 0}})
        .status_code
        == 422
    )

    patched = client.patch(
        f"/api/v1/widgets/{widget['id']}", json={"config": {"show_seconds": True}}
    ).json()
    assert patched["config"]["show_seconds"] is True

    # Clock is frontend-only: data endpoint returns null payload.
    data = client.get(f"/api/v1/widgets/{widget['id']}/data").json()
    assert data["data"] is None

    layout = {"sections": [{"id": "ambient", "widgets": [{"id": widget["id"], "size": "1x1"}]}]}
    assert client.put("/api/v1/dashboard", json=layout).status_code == 200
    assert client.get("/api/v1/dashboard").json() == layout

    assert client.delete(f"/api/v1/widgets/{widget['id']}").status_code == 204
    assert client.get("/api/v1/widgets").json() == []


def test_weather_proxy_cached(client, monkeypatch):
    calls = {"n": 0}

    def fake_open_meteo(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert "api.open-meteo.com" in str(request.url)
        return httpx.Response(
            200,
            json={
                "current": {
                    "temperature_2m": 14.2,
                    "weather_code": 3,
                    "wind_speed_10m": 12.0,
                    "relative_humidity_2m": 60,
                },
                "daily": {"temperature_2m_max": [18.0], "temperature_2m_min": [9.0]},
            },
        )

    monkeypatch.setattr(weather, "transport", httpx.MockTransport(fake_open_meteo))
    # Fresh cache per test run.
    from app.widgets.base import REGISTRY

    REGISTRY["weather"]._cache.clear()

    widget = client.post(
        "/api/v1/widgets", json={"type": "weather", "config": {"lat": 40.42, "lon": -3.7}}
    ).json()

    data = client.get(f"/api/v1/widgets/{widget['id']}/data").json()
    assert data["data"]["temp"] == 14.2
    assert data["data"]["temp_max"] == 18.0

    # Second request within the TTL never reaches Open-Meteo.
    client.get(f"/api/v1/widgets/{widget['id']}/data")
    assert calls["n"] == 1

    # The widget-less endpoint (topbar fallback) shares the same cache entry.
    data = client.get("/api/v1/weather", params={"lat": 40.42, "lon": -3.7}).json()
    assert data["data"]["temp"] == 14.2
    assert calls["n"] == 1


def test_weather_without_widget(client, monkeypatch):
    def fake_open_meteo(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 21.5, "weather_code": 0},
                "daily": {"temperature_2m_max": [25.0], "temperature_2m_min": [12.0]},
            },
        )

    monkeypatch.setattr(weather, "transport", httpx.MockTransport(fake_open_meteo))
    from app.widgets.base import REGISTRY

    REGISTRY["weather"]._cache.clear()

    data = client.get("/api/v1/weather", params={"lat": 51.5, "lon": -0.1}).json()
    assert data["data"]["temp"] == 21.5
    assert data["data"]["temp_min"] == 12.0

    # Out-of-range coordinates are a client error, not a crash.
    assert client.get("/api/v1/weather", params={"lat": 999, "lon": 0}).status_code == 422


def test_homeassistant_widget(client, monkeypatch):
    from app.widgets import homeassistant
    from app.widgets.base import REGISTRY

    def fake_ha(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer llat-token"
        assert str(request.url).endswith("/api/states")
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "sensor.processor_use",
                    "state": "17",
                    "attributes": {
                        "friendly_name": "Processor use",
                        "unit_of_measurement": "%",
                    },
                },
                {"entity_id": "light.salon", "state": "on", "attributes": {}},
                {"entity_id": "sensor.unrelated", "state": "1", "attributes": {}},
            ],
        )

    monkeypatch.setattr(homeassistant, "transport", httpx.MockTransport(fake_ha))
    REGISTRY["homeassistant"]._cache.clear()

    widget = client.post(
        "/api/v1/widgets",
        json={
            "type": "homeassistant",
            "config": {
                "base_url": "http://haos:8123",
                "token": "llat-token",
                "entities": ["sensor.processor_use", "light.salon", "sensor.gone"],
            },
        },
    ).json()

    data = client.get(f"/api/v1/widgets/{widget['id']}/data").json()["data"]
    assert data["configured"] is True
    by_id = {e["entity_id"]: e for e in data["entities"]}
    assert by_id["sensor.processor_use"]["state"] == "17"
    assert by_id["sensor.processor_use"]["unit"] == "%"
    assert by_id["sensor.processor_use"]["name"] == "Processor use"
    assert by_id["light.salon"]["state"] == "on"
    assert by_id["sensor.gone"]["state"] is None  # requested but missing in HA
    assert "sensor.unrelated" not in by_id  # only requested entities

    # Without token/entities: explicitly unconfigured, no HA call.
    unconfigured = client.post(
        "/api/v1/widgets", json={"type": "homeassistant", "config": {}}
    ).json()
    data = client.get(f"/api/v1/widgets/{unconfigured['id']}/data").json()["data"]
    assert data == {"configured": False, "entities": []}
