import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.bus import EventBus
from app.config import settings
from app.tailnet import client as ts_client
from app.tailnet import poller
from app.tailnet.acl import build_edges, parse_hujson
from app.tailnet.model import map_device


@pytest.fixture(autouse=True)
def reset_poller():
    poller.snapshot, poller.error, poller._online = None, None, None
    yield
    poller.snapshot, poller.error, poller._online = None, None, None


def dev(name, *, ip, tags=(), user="", exit_node=False, external=False):
    return map_device(
        {
            "nodeId": f"n-{name}",
            "name": f"{name}.asgard.ts.net",
            "hostname": name,
            "addresses": [ip],
            "user": user,
            "tags": list(tags),
            "online": True,
            "enabledRoutes": ["0.0.0.0/0", "::/0"] if exit_node else [],
            "external": external,
        },
        now=1000,
    )


def edge_map(edges):
    return {(e["src"], e["dst"]): e["ports"] for e in edges}


def test_parse_hujson():
    text = """
    // a line comment with a "quote
    {
      /* block
         comment */
      "hosts": {"vault": "100.64.0.9"},   // trailing comment
      "acls": [
        {"action": "accept", "src": ["*"], "dst": ["vault:443"], "note": "https://x//y"},
      ],
    }
    """
    doc = parse_hujson(text)
    assert doc["hosts"] == {"vault": "100.64.0.9"}
    assert doc["acls"][0]["note"] == "https://x//y"


def test_map_device():
    now = 1_700_000_000
    seen = datetime.fromtimestamp(now - 100, UTC).isoformat()
    device = map_device(
        {
            "id": "12345",
            "name": "mimir.asgard.ts.net",
            "hostname": "mimir",
            "addresses": ["100.64.0.7", "fd7a::7"],
            "user": "odin@example.com",
            "lastSeen": seen,
            "expires": "0001-01-01T00:00:00Z",
            "keyExpiryDisabled": True,
            "clientVersion": "1.66.4-t8f2a9",
            "enabledRoutes": ["0.0.0.0/0", "::/0", "192.168.1.0/24"],
        },
        now=now,
    )
    assert device.id == "12345"
    assert device.name == "mimir"
    assert device.online is True  # derived from lastSeen inside the window
    assert device.expires == 0
    assert device.client_version == "1.66.4"
    assert device.exit_node is True
    assert device.routes == ["192.168.1.0/24"]

    stale = map_device({"name": "x", "lastSeen": seen}, now=now + 10_000)
    assert stale.online is False


def test_acl_tag_to_tag_with_proto():
    devices = [
        dev("web", ip="100.64.0.1", tags=["tag:web"]),
        dev("db", ip="100.64.0.2", tags=["tag:db"]),
        dev("laptop", ip="100.64.0.3", user="odin@example.com"),
    ]
    policy = {
        "acls": [
            {"action": "accept", "proto": "tcp", "src": ["tag:web"], "dst": ["tag:db:5432"]}
        ]
    }
    edges, unresolved, internet = build_edges(policy, devices)
    assert edge_map(edges) == {("n-web", "n-db"): ["5432/tcp"]}
    assert not unresolved and not internet


def test_acl_groups_wildcard_and_tag_identity():
    devices = [
        dev("laptop", ip="100.64.0.1", user="odin@example.com"),
        # Tagged device owned by odin: the tag replaces user identity, so
        # neither the group nor the raw email may match it as src.
        dev("server", ip="100.64.0.2", user="odin@example.com", tags=["tag:srv"]),
    ]
    policy = {
        "groups": {
            "group:admins": ["group:gods", "loki@example.com"],
            "group:gods": ["odin@example.com"],
        },
        "acls": [{"action": "accept", "src": ["group:admins"], "dst": ["*:*"]}],
    }
    edges, _, _ = build_edges(policy, devices)
    assert edge_map(edges) == {("n-laptop", "n-server"): ["*"]}


def test_acl_hosts_and_cidr():
    devices = [dev("a", ip="100.64.0.5"), dev("vault", ip="100.64.0.9")]
    policy = {
        "hosts": {"vault-host": "100.64.0.9"},
        "acls": [
            {"action": "accept", "src": ["*"], "dst": ["vault-host:8200"]},
            {"action": "accept", "src": ["100.64.0.0/10"], "dst": ["100.64.0.5:22"]},
        ],
    }
    edges, unresolved, _ = build_edges(policy, devices)
    assert edge_map(edges) == {
        ("n-a", "n-vault"): ["8200"],
        ("n-vault", "n-a"): ["22"],
    }
    assert not unresolved


def test_autogroup_self():
    devices = [
        dev("odin-laptop", ip="100.64.0.1", user="odin@example.com"),
        dev("odin-desk", ip="100.64.0.2", user="odin@example.com"),
        dev("thor-phone", ip="100.64.0.3", user="thor@example.com"),
        dev("server", ip="100.64.0.4", tags=["tag:srv"]),
    ]
    policy = {
        "acls": [{"action": "accept", "src": ["autogroup:member"], "dst": ["autogroup:self:*"]}]
    }
    edges, _, _ = build_edges(policy, devices)
    assert edge_map(edges) == {
        ("n-odin-laptop", "n-odin-desk"): ["*"],
        ("n-odin-desk", "n-odin-laptop"): ["*"],
    }


def test_internet_needs_exit_node():
    policy = {"acls": [{"action": "accept", "src": ["*"], "dst": ["autogroup:internet:443"]}]}
    grounded = [dev("laptop", ip="100.64.0.1")]
    edges, _, internet = build_edges(policy, grounded)
    assert edges == [] and internet is False

    with_exit = [dev("laptop", ip="100.64.0.1"), dev("gate", ip="100.64.0.2", exit_node=True)]
    edges, _, internet = build_edges(policy, with_exit)
    assert internet is True
    assert edge_map(edges) == {
        ("n-gate", "internet"): ["443"],
        ("n-laptop", "internet"): ["443"],
    }


def test_grants_and_unresolved():
    devices = [
        dev("web", ip="100.64.0.1", tags=["tag:web"]),
        dev("db", ip="100.64.0.2", tags=["tag:db"]),
    ]
    policy = {
        "grants": [{"src": ["tag:web"], "dst": ["tag:db"], "ip": ["tcp:5432", "udp:53"]}],
        "acls": [{"action": "accept", "src": ["autogroup:admin", "banana"], "dst": ["tag:db:1"]}],
    }
    edges, unresolved, _ = build_edges(policy, devices)
    assert edge_map(edges) == {("n-web", "n-db"): ["53/udp", "5432/tcp"]}
    assert unresolved == {"autogroup:admin", "banana"}


def raw_fixture_doc():
    return {
        "tailnet": "asgard.ts.net",
        "devices": [
            {
                "nodeId": "n-mimir",
                "name": "mimir.asgard.ts.net",
                "addresses": ["100.64.0.7"],
                "tags": ["tag:server"],
                "online": True,
            },
            {
                "nodeId": "n-laptop",
                "name": "laptop.asgard.ts.net",
                "addresses": ["100.64.0.8"],
                "user": "odin@example.com",
                "online": True,
            },
        ],
        "policy": {"acls": [{"action": "accept", "src": ["*"], "dst": ["*:*"]}]},
    }


def test_unconfigured_rest_shape(client):
    state = client.get("/api/v1/tailnet").json()
    assert state["configured"] is False
    assert state["devices"] == [] and state["edges"] == []
    # Refresh without config stays a no-op.
    assert client.post("/api/v1/tailnet/refresh").json()["configured"] is False


def test_sweep_from_api_and_rest(client, monkeypatch):
    doc = raw_fixture_doc()

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        if "/devices" in request.url.path:
            return httpx.Response(200, json={"devices": doc["devices"]})
        if request.url.path.endswith("/acl"):
            # HuJSON on purpose: exercises the non-JSON fallback.
            return httpx.Response(
                200,
                text='// policy\n{"acls": [{"action": "accept", "src": ["*"], "dst": ["*:*"],}],}',
            )
        return httpx.Response(404)

    monkeypatch.setattr(ts_client, "transport", httpx.MockTransport(responder))
    monkeypatch.setattr(settings, "tailscale_api_key", "test-token")

    asyncio.run(poller.sweep_once())
    state = client.get("/api/v1/tailnet").json()
    assert state["configured"] is True
    assert state["source"] == "api"
    assert state["tailnet"] == "asgard.ts.net"  # derived from the MagicDNS suffix
    assert [d["name"] for d in state["devices"]] == ["laptop", "mimir"]
    assert edge_map(state["edges"]) == {
        ("n-laptop", "n-mimir"): ["*"],
        ("n-mimir", "n-laptop"): ["*"],
    }
    assert state["policy"]["rules"] == 1


def test_sweep_error_keeps_stale_snapshot(client, monkeypatch):
    monkeypatch.setattr(settings, "tailscale_api_key", "test-token")
    monkeypatch.setattr(
        ts_client,
        "transport",
        httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    poller.snapshot = {"source": "api", "tailnet": "old", "fetched_at": 1, "devices": [],
                       "edges": [], "internet": False, "policy": None}
    asyncio.run(poller.sweep_once())
    state = client.get("/api/v1/tailnet").json()
    assert state["tailnet"] == "old"
    assert "500" in state["error"]


def test_refresh_from_fixture(client, tmp_path, monkeypatch):
    path = tmp_path / "tailnet.json"
    path.write_text(json.dumps(raw_fixture_doc()))
    monkeypatch.setattr(settings, "tailnet_fixture", path)
    state = client.post("/api/v1/tailnet/refresh").json()
    assert state["configured"] is True
    assert state["source"] == "fixture"
    assert state["tailnet"] == "asgard.ts.net"
    assert len(state["devices"]) == 2


def test_transition_events(tmp_path, monkeypatch):
    bus = EventBus()
    queue = bus.subscribe()
    path = tmp_path / "tailnet.json"
    doc = raw_fixture_doc()
    path.write_text(json.dumps(doc))
    monkeypatch.setattr(settings, "tailnet_fixture", path)

    asyncio.run(poller.sweep_once(bus))
    first = [queue.get_nowait() for _ in range(queue.qsize())]
    # First sweep announces the graph, but never storms device events.
    assert [e.topic for e in first] == ["tailnet.updated"]

    doc["devices"][0]["online"] = False
    path.write_text(json.dumps(doc))
    asyncio.run(poller.sweep_once(bus))
    second = [queue.get_nowait() for _ in range(queue.qsize())]
    assert [e.topic for e in second] == ["tailnet.device.offline", "tailnet.updated"]
    assert second[0].data["subject"] == "mimir"
