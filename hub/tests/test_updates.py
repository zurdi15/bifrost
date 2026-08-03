import asyncio
import json

import httpx

from app.updates import watcher
from tests.conftest import agent_headers, hello_frame
from tests.test_containers import containers_full_frame, wait_for
from tests.test_gateway import container


def test_split_image():
    assert watcher.split_image("ghcr.io/x/y:1.2.3") == ("ghcr.io", "x/y", "1.2.3")
    assert watcher.split_image("pihole/pihole:2026.02.0") == (
        "docker.io", "pihole/pihole", "2026.02.0",
    )
    assert watcher.split_image("mariadb:11.3") == ("docker.io", "library/mariadb", "11.3")
    # Uncomparable: latest, digests, no tag.
    assert watcher.split_image("caddy-caddy") is None
    assert watcher.split_image("x/y:latest") is None
    assert watcher.split_image("x/y@sha256:abc") is None


def test_sweep_finds_newer_tags(client, monkeypatch):
    def responder(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://ghcr.io/token"):
            return httpx.Response(200, json={"token": "anon"})
        if url.startswith("https://ghcr.io/v2/z/app/tags/list"):
            assert request.headers["Authorization"] == "Bearer anon"
            return httpx.Response(200, json={"tags": ["0.9.0", "1.1.0", "1.2.0", "latest"]})
        if "hub.docker.com" in url:
            return httpx.Response(
                200, json={"results": [{"name": "11.3.2"}, {"name": "11.2.0"}]}
            )
        return httpx.Response(404)

    monkeypatch.setattr(watcher, "transport", httpx.MockTransport(responder))
    watcher.results.clear()

    with client.websocket_connect("/api/ws/agent", headers=agent_headers()) as ws:
        ws.send_text(hello_frame())
        json.loads(ws.receive_text())
        ws.send_text(
            containers_full_frame(
                1,
                [
                    {**container("app", ["8000:8000/tcp"], {}), "image": "ghcr.io/z/app:1.1.0"},
                    {**container("db", [], {}), "image": "mariadb:11.3.2"},
                ],
            )
        )
        wait_for(lambda: client.get("/api/v1/containers").json() or None)

        asyncio.run(watcher.sweep_once())
        assert watcher.results == {"ghcr.io/z/app:1.1.0": "1.2.0"}

        # The card carries the newer tag; up-to-date images carry nothing.
        cards = {c["name"]: c for c in client.get("/api/v1/containers").json()}
        assert cards["app"]["update"] == "1.2.0"
        assert cards["db"]["update"] is None

    watcher.results.clear()
