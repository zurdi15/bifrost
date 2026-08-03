"""Zero-config service icons: names are matched against the selfh.st icon
index (https://selfh.st/icons/, ~3k self-hosted apps), proxied and cached by
the hub so the browser only ever fetches the final image. Matching flattens
both sides (lowercase, alphanumerics only), so container 'pihole' finds the
canonical 'pi-hole' reference.
"""

import logging
import re
import time

import httpx
from fastapi import APIRouter, Query

logger = logging.getLogger("bifrost.icons")

router = APIRouter()

INDEX_URL = "https://cdn.jsdelivr.net/gh/selfhst/icons/index.json"
CDN_BASE = "https://cdn.jsdelivr.net/gh/selfhst/icons"
CACHE_TTL_S = 24 * 3600
RETRY_AFTER_S = 300
MAX_NAMES = 100

# Injectable for tests.
transport: httpx.AsyncBaseTransport | None = None

_flatten = re.compile(r"[^a-z0-9]+")

# flat key → icon URL. None sentinels: time.monotonic() starts near 0 on a
# freshly booted host, so 0.0 would read as "just fetched/failed".
_index: dict[str, str] = {}
_fetched_at: float | None = None
_retry_at: float | None = None


def flatten(name: str) -> str:
    return _flatten.sub("", name.lower())


def _build_index(entries: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in entries:
        reference = entry.get("Reference") or ""
        if not reference:
            continue
        ext = "svg" if entry.get("SVG") == "Yes" else "png"
        url = f"{CDN_BASE}/{ext}/{reference}.{ext}"
        for key in (flatten(reference), flatten(entry.get("Name") or "")):
            if key and key not in mapping:
                mapping[key] = url
    return mapping


async def _load_index() -> dict[str, str]:
    global _index, _fetched_at, _retry_at
    now = time.monotonic()
    if _index and _fetched_at is not None and now - _fetched_at < CACHE_TTL_S:
        return _index
    if _retry_at is not None and now < _retry_at:
        return _index  # possibly stale — better than hammering the CDN
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            response = await client.get(INDEX_URL)
            response.raise_for_status()
            entries = response.json()
    except Exception as exc:
        logger.warning("icon index fetch failed: %s", exc)
        _retry_at = now + RETRY_AFTER_S
        return _index
    _index = _build_index(entries)
    _fetched_at, _retry_at = now, None
    return _index


@router.get("/icons")
async def resolve_icons(
    names: str = Query("", max_length=4000),
) -> dict[str, str | None]:
    """Comma-separated names → icon URL or null, in one round-trip."""
    requested = [n.strip() for n in names.split(",") if n.strip()][:MAX_NAMES]
    if not requested:
        return {}
    index = await _load_index()
    return {name: index.get(flatten(name)) for name in requested}


# ── Portal favicons: the node UI itself is the icon source ──────────────────
# uuid → (expires_at, media_type, bytes) — None body caches the miss.
_portal_cache: dict[str, tuple[float, str | None, bytes | None]] = {}

FAVICON_PATHS = ("/favicon.svg", "/favicon.ico", "/favicon.png", "/apple-touch-icon.png")


def _portal_base(session, node) -> str | None:  # noqa: ANN001
    from sqlalchemy import select

    from app.api.gateway import _endpoint_upstream
    from app.models import EndpointCheck

    if node.kind == "endpoint":
        checks = list(
            session.scalars(select(EndpointCheck).where(EndpointCheck.node_id == node.id))
        )
        upstream = _endpoint_upstream(checks)
        if upstream is None:
            return None
        return f"http://{upstream[0]}:{upstream[1]}"
    if node.ui_port:
        return f"http://{node.name}:{node.ui_port}"
    return None


@router.get("/icons/portal/{uuid}")
async def portal_icon(uuid: str):  # noqa: ANN201
    from fastapi import HTTPException, Response
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import Node

    cached = _portal_cache.get(uuid)
    if cached and cached[0] > time.monotonic():
        if cached[2] is None:
            raise HTTPException(status_code=404)
        return Response(content=cached[2], media_type=cached[1])

    with session_scope() as session:
        node = session.scalar(select(Node).where(Node.uuid == uuid))
        base = _portal_base(session, node) if node else None

    body: bytes | None = None
    media: str | None = None
    if base is not None:
        async with httpx.AsyncClient(
            timeout=6, transport=transport, verify=False, follow_redirects=True
        ) as client:
            for path in FAVICON_PATHS:
                try:
                    response = await client.get(base + path)
                except httpx.HTTPError:
                    continue
                kind = response.headers.get("content-type", "")
                if response.status_code == 200 and response.content and "text/html" not in kind:
                    body = response.content
                    media = kind or "image/x-icon"
                    break
    _portal_cache[uuid] = (time.monotonic() + CACHE_TTL_S, media, body)
    if body is None:
        raise HTTPException(status_code=404)
    return Response(content=body, media_type=media)
