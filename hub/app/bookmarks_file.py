"""Declarative bookmarks: a YAML file the hub ingests, so a dashboard's
links replicate across deployments by shipping one file.

Two shapes, mixable in the same top-level list:

    - name: Proxmox            # flat entry
      url: https://pve.local
      icon: "🖥️"               # optional — emoji or image URL
    - group: media             # group block
      items:
        - name: RomM
          url: https://romm.local

File entries own their rows (source='file'): the sync replaces them to
mirror the file exactly, while UI-created bookmarks are left untouched.
Synced on startup and whenever the file's mtime changes.
"""

import asyncio
import logging
from pathlib import Path

import yaml
from sqlalchemy import delete, select

from app.bus import EventBus
from app.config import settings
from app.db import session_scope
from app.models import Bookmark

logger = logging.getLogger("bifrost.bookmarks")

WATCH_INTERVAL_S = 30


def parse_bookmarks_yaml(text: str) -> list[dict]:
    """→ [{name, url, icon, group}] in file order. Raises ValueError on junk."""
    data = yaml.safe_load(text)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("bookmarks file must be a YAML list")

    entries: list[dict] = []

    def add(item: dict, group: str | None) -> None:
        if not isinstance(item, dict) or not item.get("name") or not item.get("url"):
            raise ValueError(f"bookmark needs name and url: {item!r}")
        entries.append(
            {
                "name": str(item["name"]).strip(),
                "url": str(item["url"]).strip(),
                "icon": str(item["icon"]).strip() if item.get("icon") else None,
                "group": str(group).strip() if group else None,
            }
        )

    for block in data:
        if isinstance(block, dict) and "items" in block:
            for item in block.get("items") or []:
                add(item, block.get("group"))
        else:
            add(block, block.get("group") if isinstance(block, dict) else None)
    return entries


def sync_file_bookmarks(entries: list[dict]) -> bool:
    """Mirror source='file' rows to the entries. Returns whether rows changed."""
    with session_scope() as session:
        existing = [
            {
                "name": b.name,
                "url": b.url,
                "icon": b.icon,
                "group": b.group_name,
            }
            for b in session.scalars(
                select(Bookmark)
                .where(Bookmark.source == "file")
                .order_by(Bookmark.position)
            )
        ]
        if existing == entries:
            return False
        session.execute(delete(Bookmark).where(Bookmark.source == "file"))
        for position, entry in enumerate(entries):
            session.add(
                Bookmark(
                    name=entry["name"],
                    url=entry["url"],
                    icon=entry["icon"],
                    group_name=entry["group"],
                    position=position,
                    source="file",
                )
            )
    return True


def load_bookmarks_file(path: Path) -> bool:
    """One parse+sync pass; parse errors keep the previous state."""
    try:
        entries = parse_bookmarks_yaml(path.read_text())
    except FileNotFoundError:
        entries = []
    except (ValueError, OSError, yaml.YAMLError) as exc:
        logger.warning("bookmarks file %s ignored: %s", path, exc)
        return False
    if sync_file_bookmarks(entries):
        logger.info("bookmarks synced from %s (%d entries)", path, len(entries))
        return True
    return False


async def bookmarks_file_watcher(bus: EventBus) -> None:
    """Startup sync + resync whenever the file's mtime changes."""
    path = settings.bookmarks_file_path
    if await asyncio.to_thread(load_bookmarks_file, path):
        bus.publish("bookmarks.updated", {})
    last_mtime = await asyncio.to_thread(_mtime, path)
    while True:
        await asyncio.sleep(WATCH_INTERVAL_S)
        mtime = await asyncio.to_thread(_mtime, path)
        if mtime == last_mtime:
            continue
        last_mtime = mtime
        if await asyncio.to_thread(load_bookmarks_file, path):
            bus.publish("bookmarks.updated", {})


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None
