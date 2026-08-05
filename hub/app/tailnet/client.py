"""Tailnet document sources: the Tailscale admin API, or a canned fixture.

The fixture path serves a {"devices": [...], "policy": {...}} document (JSON
or HuJSON) so the seeded dev stack, demos and tests can run the whole section
without a real tailnet. Both sources produce the exact same raw shapes."""

import asyncio
import json
from pathlib import Path

import httpx

from app.tailnet.acl import parse_hujson

API_BASE = "https://api.tailscale.com/api/v2"

# Injectable for tests.
transport: httpx.AsyncBaseTransport | None = None


async def fetch(api_key: str, tailnet: str) -> tuple[list[dict], dict]:
    """(raw devices, policy) from the admin API. "-" = the token's tailnet."""
    name = tailnet or "-"
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=15, transport=transport, headers=headers) as client:
        devices_resp = await client.get(
            f"{API_BASE}/tailnet/{name}/devices", params={"fields": "all"}
        )
        devices_resp.raise_for_status()
        acl_resp = await client.get(
            f"{API_BASE}/tailnet/{name}/acl", headers={"Accept": "application/json"}
        )
        acl_resp.raise_for_status()
    try:
        policy = acl_resp.json()
    except json.JSONDecodeError:
        policy = parse_hujson(acl_resp.text)
    return devices_resp.json().get("devices") or [], policy


async def load_fixture(path: Path) -> tuple[list[dict], dict, str]:
    """(raw devices, policy, tailnet name) from a fixture document."""
    doc = parse_hujson(await asyncio.to_thread(path.read_text))
    return doc.get("devices") or [], doc.get("policy") or {}, doc.get("tailnet") or ""
