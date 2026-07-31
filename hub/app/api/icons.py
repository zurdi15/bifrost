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
