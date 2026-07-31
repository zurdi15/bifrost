import asyncio

import httpx

from app.bus import EventBus
from app.checks.runner import _execute_due_checks, run_check, run_http_check
from tests.conftest import agent_headers, hello_frame  # noqa: F401  (fixture deps)


def test_create_endpoint_and_listing(client):
    created = client.post(
        "/api/v1/nodes/endpoints",
        json={
            "name": "haos",
            "checks": [
                {"kind": "http", "target": "http://haos:8123/manifest.json"},
                {"kind": "ping", "target": "haos"},
            ],
        },
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["kind"] == "endpoint"
    assert len(payload["checks"]) == 2

    nodes = client.get("/api/v1/nodes").json()
    endpoint = next(n for n in nodes if n["kind"] == "endpoint")
    assert endpoint["name"] == "haos"
    assert endpoint["checks"][0]["kind"] == "http"

    # Agent-style nodes carry no checks.
    assert client.post(
        "/api/v1/nodes/endpoints", json={"name": "bad", "checks": []}
    ).status_code == 422
    assert client.post(
        "/api/v1/nodes/endpoints",
        json={"name": "bad", "checks": [{"kind": "smoke", "target": "x"}]},
    ).status_code == 422


def test_http_check_with_mock_transport():
    async def scenario():
        ok_transport = httpx.MockTransport(lambda request: httpx.Response(200))
        ok, latency = await run_http_check("http://x/health", 5, None, ok_transport)
        assert ok and latency is not None

        strict = httpx.MockTransport(lambda request: httpx.Response(302))
        ok, _ = await run_http_check("http://x", 5, 200, strict)
        assert not ok

        boom = httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("x")))
        ok, latency = await run_http_check("http://x", 5, None, boom)
        assert not ok and latency is None

    asyncio.run(scenario())


def test_tcp_check_against_real_socket():
    async def scenario():
        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            ok, latency = await run_check("tcp", f"127.0.0.1:{port}", 5)
            assert ok and latency is not None
        finally:
            server.close()
            await server.wait_closed()

        ok, _ = await run_check("tcp", "127.0.0.1:1", 1)  # closed port
        assert not ok
        ok, _ = await run_check("tcp", "garbage", 1)
        assert not ok

    asyncio.run(scenario())


class StubMetrics:
    def __init__(self) -> None:
        self.samples: list = []

    def enqueue(self, node_id, ts, samples) -> None:  # noqa: ANN001
        self.samples.append((node_id, samples))


def test_execute_due_checks_drives_node_status(client):
    async def scenario():
        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        created = client.post(
            "/api/v1/nodes/endpoints",
            json={
                "name": "gateway",
                "checks": [{"kind": "tcp", "target": f"127.0.0.1:{port}", "interval_s": 1}],
            },
        ).json()

        bus = EventBus()
        events = bus.subscribe()
        metrics = StubMetrics()

        await _execute_due_checks(bus, metrics)
        node = client.get(f"/api/v1/nodes/{created['uuid']}").json()
        assert node["status"] == "online"
        assert node["checks"][0]["last_ok"] is True
        assert node["checks"][0]["last_latency_ms"] is not None
        assert metrics.samples and metrics.samples[0][1][0][0] == "check.latency_ms"
        topics = {events.get_nowait().topic for _ in range(events.qsize())}
        assert {"node.status", "endpoint.status"} <= topics

        # Target dies → next due cycle flips the node offline.
        server.close()
        await server.wait_closed()
        await asyncio.sleep(1.1)  # let the interval elapse
        await _execute_due_checks(bus, metrics)
        node = client.get(f"/api/v1/nodes/{created['uuid']}").json()
        assert node["status"] == "offline"

    asyncio.run(scenario())
