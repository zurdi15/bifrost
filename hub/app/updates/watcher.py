"""Newer-tag watch over every running image.

Read-only by design: bifrost points at what is behind, you decide when to
move. Only semver-ish tags are compared (a container pinned to :latest or a
digest has nothing to compare), and results live in memory — re-derived on
every sweep, nothing to migrate. A fresh detection publishes image.update so
alert rules can forward it."""

import asyncio
import logging
import re

import httpx
from sqlalchemy import select

from app.bus import EventBus
from app.db import session_scope
from app.models import Container

logger = logging.getLogger("bifrost.updates")

INTERVAL_S = 6 * 3600
STARTUP_DELAY_S = 90

# image ref ("ghcr.io/x/y:1.2.3") → newest semver tag seen upstream
results: dict[str, str] = {}

# Injectable for tests.
transport: httpx.AsyncBaseTransport | None = None

SEMVER = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?$")


def parse_semver(tag: str) -> tuple[int, int, int] | None:
    match = SEMVER.match(tag)
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def split_image(ref: str) -> tuple[str, str, str] | None:
    """"ghcr.io/x/y:1.2" → (registry, repo, tag); None when uncomparable."""
    if not ref or "@" in ref:
        return None
    name, sep, tag = ref.rpartition(":")
    if not sep or "/" in tag or parse_semver(tag) is None:
        return None
    first = name.split("/")[0]
    if "." in first or first == "localhost":
        registry, repo = first, name[len(first) + 1 :]
    else:
        registry, repo = "docker.io", name if "/" in name else f"library/{name}"
    return registry, repo, tag


async def list_tags(client: httpx.AsyncClient, registry: str, repo: str) -> list[str]:
    if registry == "docker.io":
        response = await client.get(
            f"https://hub.docker.com/v2/repositories/{repo}/tags",
            params={"page_size": 100, "ordering": "last_updated"},
        )
        response.raise_for_status()
        return [t["name"] for t in response.json().get("results", [])]
    # Generic registry v2 with anonymous pull token (ghcr.io and friends).
    token_response = await client.get(
        f"https://{registry}/token",
        params={"scope": f"repository:{repo}:pull", "service": registry},
    )
    headers = {}
    if token_response.status_code == 200:
        token = token_response.json().get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    response = await client.get(f"https://{registry}/v2/{repo}/tags/list", headers=headers)
    response.raise_for_status()
    return response.json().get("tags") or []


async def sweep_once(bus: EventBus | None = None) -> None:
    with session_scope() as session:
        images = set(session.scalars(select(Container.image).distinct()))
    fresh: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=15, transport=transport) as client:
        for ref in sorted(i for i in images if i):
            parsed = split_image(ref)
            if parsed is None:
                continue
            registry, repo, tag = parsed
            current = parse_semver(tag)
            try:
                tags = await list_tags(client, registry, repo)
            except (httpx.HTTPError, ValueError) as exc:
                logger.debug("tag list failed for %s: %s", ref, exc)
                continue
            versions = [(parse_semver(t), t) for t in tags]
            newer = max(((v, t) for v, t in versions if v and v > current), default=None)
            if newer is not None:
                fresh[ref] = newer[1]
                if bus is not None and results.get(ref) != newer[1]:
                    bus.publish("image.update", {"image": ref, "latest": newer[1]})
    results.clear()
    results.update(fresh)


async def update_watch(bus: EventBus) -> None:
    await asyncio.sleep(STARTUP_DELAY_S)
    while True:
        try:
            await sweep_once(bus)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("image update sweep failed")
        await asyncio.sleep(INTERVAL_S)
