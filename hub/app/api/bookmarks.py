
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bookmarks_file import entry_of, file_lock, write_bookmarks_file
from app.db import get_session
from app.models import Bookmark

router = APIRouter()


def _to_dict(bookmark: Bookmark) -> dict:
    return {
        "id": bookmark.id,
        "name": bookmark.name,
        "url": bookmark.url,
        "icon": bookmark.icon,
        "group": bookmark.group_name,
        "position": bookmark.position,
        "source": bookmark.source,
    }


def _file_entries(session: Session) -> list[dict]:
    """Current file-backed set in display order — what the YAML must say.
    Autoflush folds in the pending mutation of the calling endpoint."""
    rows = session.scalars(
        select(Bookmark)
        .where(Bookmark.source == "file")
        .order_by(Bookmark.position, Bookmark.name)
    ).all()
    return [entry_of(b) for b in rows]


@router.get("/bookmarks")
def list_bookmarks(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.scalars(
        select(Bookmark).order_by(Bookmark.position, Bookmark.name)
    ).all()
    return [_to_dict(b) for b in rows]


class BookmarkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    icon: str | None = None
    group: str | None = None


class BookmarkPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=1, max_length=2000)
    icon: str | None = None
    group: str | None = None
    position: int | None = None


class BookmarkOrder(BaseModel):
    ids: list[int]


@router.post("/bookmarks", status_code=201)
def create_bookmark(
    body: BookmarkCreate, request: Request, session: Session = Depends(get_session)
) -> dict:
    last = session.scalar(
        select(Bookmark.position).order_by(Bookmark.position.desc()).limit(1)
    )
    bookmark = Bookmark(
        name=body.name.strip(),
        url=body.url.strip(),
        icon=(body.icon or "").strip() or None,
        group_name=(body.group or "").strip() or None,
        position=(last or 0) + 1,
        source="file",
    )
    with file_lock:
        session.add(bookmark)
        session.flush()
        # Write-through: the UI's bookmark lands in bookmarks.yml. If the
        # file can't be written, the bookmark lives in the DB only.
        if not write_bookmarks_file(_file_entries(session)):
            bookmark.source = "ui"
        session.commit()
    request.app.state.bus.publish("bookmarks.updated", {})
    return _to_dict(bookmark)


@router.patch("/bookmarks/{bookmark_id}")
def patch_bookmark(
    bookmark_id: int,
    body: BookmarkPatch,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    with file_lock:
        bookmark = session.get(Bookmark, bookmark_id)
        if bookmark is None:
            raise HTTPException(404)
        if body.name is not None:
            bookmark.name = body.name.strip()
        if body.url is not None:
            bookmark.url = body.url.strip()
        if body.icon is not None:
            bookmark.icon = body.icon.strip() or None
        if body.group is not None:
            bookmark.group_name = body.group.strip() or None
        if body.position is not None:
            bookmark.position = body.position
        if bookmark.source == "file" and not write_bookmarks_file(
            _file_entries(session)
        ):
            session.rollback()
            raise HTTPException(409, detail="bookmarks.yml is not writable")
        session.commit()
    request.app.state.bus.publish("bookmarks.updated", {})
    return _to_dict(bookmark)


@router.delete("/bookmarks/{bookmark_id}", status_code=204)
def delete_bookmark(
    bookmark_id: int, request: Request, session: Session = Depends(get_session)
) -> None:
    with file_lock:
        bookmark = session.get(Bookmark, bookmark_id)
        if bookmark is None:
            raise HTTPException(404)
        source = bookmark.source
        session.delete(bookmark)
        if source == "file" and not write_bookmarks_file(_file_entries(session)):
            session.rollback()
            raise HTTPException(409, detail="bookmarks.yml is not writable")
        session.commit()
    request.app.state.bus.publish("bookmarks.updated", {})


@router.put("/bookmarks/order", status_code=204)
def order_bookmarks(
    body: BookmarkOrder, request: Request, session: Session = Depends(get_session)
) -> None:
    """Full desired order in one call (per-row position patches would need a
    file rewrite each). Unknown ids are ignored; unlisted rows keep theirs."""
    with file_lock:
        rows = {b.id: b for b in session.scalars(select(Bookmark)).all()}
        ordered = [rows[i] for i in body.ids if i in rows]
        for index, bookmark in enumerate(ordered):
            bookmark.position = index
        if any(b.source == "file" for b in ordered) and not write_bookmarks_file(
            _file_entries(session)
        ):
            session.rollback()
            raise HTTPException(409, detail="bookmarks.yml is not writable")
        session.commit()
    request.app.state.bus.publish("bookmarks.updated", {})
