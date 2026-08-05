"""Tailscale device mapping: raw admin-API JSON → the shape the UI eats.

Timestamps become integer epoch seconds at this boundary (RFC3339 in, ints
out, per the repo-wide rule). Online-ness is derived from lastSeen when the
document does not carry an explicit flag — the devices endpoint has no live
socket to consult, but connected peers refresh lastSeen continuously."""

import time
from dataclasses import asdict, dataclass
from datetime import datetime

# lastSeen refreshes every couple of minutes for connected peers; anything
# older than this window reads as offline.
ONLINE_WINDOW_S = 300

DEFAULT_ROUTES = {"0.0.0.0/0", "::/0"}


def parse_ts(value: str | None) -> int:
    # Tailscale uses year-1 sentinels for "never".
    if not value or value.startswith("0001-"):
        return 0
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return 0


@dataclass(slots=True)
class Device:
    id: str
    name: str
    fqdn: str
    hostname: str
    ips: list[str]
    os: str
    user: str
    tags: list[str]
    online: bool
    last_seen: int
    expires: int
    key_expiry_disabled: bool
    client_version: str
    update_available: bool
    authorized: bool
    external: bool
    exit_node: bool
    routes: list[str]
    blocks_incoming: bool

    def as_dict(self) -> dict:
        return asdict(self)


def map_device(raw: dict, now: int | None = None) -> Device:
    now = int(time.time()) if now is None else now
    last_seen = parse_ts(raw.get("lastSeen"))
    if "online" in raw:
        online = bool(raw["online"])
    else:
        online = bool(last_seen) and now - last_seen < ONLINE_WINDOW_S
    enabled_routes = list(raw.get("enabledRoutes") or [])
    fqdn = raw.get("name") or raw.get("hostname") or ""
    return Device(
        id=str(raw.get("nodeId") or raw.get("id") or fqdn),
        name=fqdn.split(".")[0],
        fqdn=fqdn,
        hostname=raw.get("hostname") or "",
        ips=list(raw.get("addresses") or []),
        os=raw.get("os") or "",
        user=raw.get("user") or "",
        tags=list(raw.get("tags") or []),
        online=online,
        last_seen=last_seen,
        expires=parse_ts(raw.get("expires")),
        key_expiry_disabled=bool(raw.get("keyExpiryDisabled")),
        client_version=(raw.get("clientVersion") or "").split("-")[0],
        update_available=bool(raw.get("updateAvailable")),
        authorized=bool(raw.get("authorized", True)),
        external=bool(raw.get("external")),
        exit_node=any(r in DEFAULT_ROUTES for r in enabled_routes),
        routes=[r for r in enabled_routes if r not in DEFAULT_ROUTES],
        blocks_incoming=bool(raw.get("blocksIncomingConnections")),
    )
