import httpx

from app.api import icons


def make_transport(entries: list[dict], calls: list[int]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=entries)

    return httpx.MockTransport(handler)


INDEX = [
    {"Name": "Pi-hole", "Reference": "pi-hole", "SVG": "Yes"},
    {"Name": "RomM", "Reference": "romm", "SVG": "Yes"},
    {"Name": "Home Assistant", "Reference": "home-assistant", "SVG": "No", "PNG": "Yes"},
]


def reset_cache() -> None:
    icons._index = {}
    icons._fetched_at = None
    icons._retry_at = None


def test_resolve_flattens_both_sides(client, monkeypatch):
    reset_cache()
    calls: list[int] = []
    monkeypatch.setattr(icons, "transport", make_transport(INDEX, calls))

    got = client.get(
        "/api/v1/icons", params={"names": "pihole,PiHole,romm,home_assistant,nope"}
    ).json()
    # Container 'pihole' matches the canonical 'pi-hole' reference.
    assert got["pihole"] == f"{icons.CDN_BASE}/svg/pi-hole.svg"
    assert got["PiHole"] == got["pihole"]
    assert got["romm"] == f"{icons.CDN_BASE}/svg/romm.svg"
    # No SVG available → png URL.
    assert got["home_assistant"] == f"{icons.CDN_BASE}/png/home-assistant.png"
    assert got["nope"] is None

    # Second request is served from the cached index.
    client.get("/api/v1/icons", params={"names": "romm"})
    assert len(calls) == 1


def test_resolve_survives_index_failure(client, monkeypatch):
    reset_cache()
    monkeypatch.setattr(
        icons, "transport", httpx.MockTransport(lambda r: httpx.Response(500))
    )
    got = client.get("/api/v1/icons", params={"names": "romm"}).json()
    assert got == {"romm": None}
    assert client.get("/api/v1/icons", params={"names": ""}).json() == {}
