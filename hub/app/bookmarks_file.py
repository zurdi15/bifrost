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
mirror the file exactly. Synced on startup and whenever the file's mtime
changes.

The mirror is two-way: UI creates/edits/deletes write through to the file
(DB first, then `write_bookmarks_file` regenerates the YAML), so the file
always holds the full set of links. Hand-written comments do not survive a
UI write. `source='ui'` rows only appear when the file isn't writable.
"""

import asyncio
import logging
import threading
from pathlib import Path

import yaml
from sqlalchemy import delete, select

from app.bus import EventBus
from app.config import settings
from app.db import session_scope
from app.models import Bookmark

logger = logging.getLogger("bifrost.bookmarks")

WATCH_INTERVAL_S = 30

# Serializes file read-modify-write between the API endpoints (threadpool)
# and the watcher (asyncio.to_thread) so neither sees a half-applied state.
file_lock = threading.Lock()


def resolve_bookmarks_path() -> Path:
    """Explicit BIFROST_BOOKMARKS_FILE wins; otherwise whichever of
    bookmarks.yml / bookmarks.yaml exists in the data dir (.yml default)."""
    if settings.bookmarks_file:
        return settings.bookmarks_file
    for candidate in ("bookmarks.yml", "bookmarks.yaml"):
        path = settings.data_dir / candidate
        if path.is_file():
            return path
    return settings.data_dir / "bookmarks.yml"


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


def entry_of(bookmark: Bookmark) -> dict:
    """Row → the parse_bookmarks_yaml entry shape."""
    return {
        "name": bookmark.name,
        "url": bookmark.url,
        "icon": bookmark.icon,
        "group": bookmark.group_name,
    }


def dump_bookmarks_yaml(entries: list[dict]) -> str:
    """Inverse of parse_bookmarks_yaml: consecutive same-group entries fold
    into one group block, ungrouped entries stay flat."""
    blocks: list[dict] = []
    for entry in entries:
        item: dict = {"name": entry["name"], "url": entry["url"]}
        if entry.get("icon"):
            item["icon"] = entry["icon"]
        group = entry.get("group")
        if not group:
            blocks.append(item)
        elif blocks and blocks[-1].get("group") == group:
            blocks[-1]["items"].append(item)
        else:
            blocks.append({"group": group, "items": [item]})
    return yaml.safe_dump(blocks, allow_unicode=True, sort_keys=False)


def write_bookmarks_file(entries: list[dict]) -> bool:
    """Mirror UI-mutated entries into the YAML (the DB changed first).
    False when the file can't be written — the caller keeps the change
    DB-only. Call with file_lock held."""
    path = resolve_bookmarks_path()
    if path.is_dir():
        return False
    try:
        path.write_text(dump_bookmarks_yaml(entries))
    except OSError as exc:
        logger.warning("bookmarks write-through to %s failed: %s", path, exc)
        return False
    return True


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
    if path.is_dir():
        # The classic Docker footgun: binding a file that didn't exist on the
        # host yet makes Docker create a directory in its place.
        logger.warning(
            "bookmarks path %s is a directory, not a file — if you bind-mount "
            "it, make sure the host file exists before the container starts",
            path,
        )
        return False
    with file_lock:
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
    """Startup sync + resync whenever the file's mtime changes. The path is
    re-resolved every tick so a file created after startup (either .yml or
    .yaml) gets picked up without a restart."""
    path = await asyncio.to_thread(resolve_bookmarks_path)
    if await asyncio.to_thread(load_bookmarks_file, path):
        bus.publish("bookmarks.updated", {})
    last_state = (path, await asyncio.to_thread(_mtime, path))
    while True:
        await asyncio.sleep(WATCH_INTERVAL_S)
        path = await asyncio.to_thread(resolve_bookmarks_path)
        state = (path, await asyncio.to_thread(_mtime, path))
        if state == last_state:
            continue
        last_state = state
        if await asyncio.to_thread(load_bookmarks_file, path):
            bus.publish("bookmarks.updated", {})


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None
