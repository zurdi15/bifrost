
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    }


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


@router.post("/bookmarks", status_code=201)
def create_bookmark(
    body: BookmarkCreate, session: Session = Depends(get_session)
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
    )
    session.add(bookmark)
    session.flush()
    return _to_dict(bookmark)


@router.patch("/bookmarks/{bookmark_id}")
def patch_bookmark(
    bookmark_id: int, body: BookmarkPatch, session: Session = Depends(get_session)
) -> dict:
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
    session.flush()
    return _to_dict(bookmark)


@router.delete("/bookmarks/{bookmark_id}", status_code=204)
def delete_bookmark(bookmark_id: int, session: Session = Depends(get_session)) -> None:
    bookmark = session.get(Bookmark, bookmark_id)
    if bookmark is None:
        raise HTTPException(404)
    session.delete(bookmark)
