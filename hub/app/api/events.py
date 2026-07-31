import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import DbEvent

router = APIRouter()


@router.get("/events")
def list_events(
    session: Session = Depends(get_session),
    from_ts: int | None = Query(default=None, alias="from"),
    kind: str | None = None,
    limit: int = Query(default=100, le=1000),
) -> list[dict]:
    stmt = select(DbEvent).order_by(DbEvent.ts.desc(), DbEvent.id.desc()).limit(limit)
    if from_ts is not None:
        stmt = stmt.where(DbEvent.ts >= from_ts)
    if kind is not None:
        stmt = stmt.where(DbEvent.kind == kind)
    return [
        {
            "id": e.id,
            "ts": e.ts,
            "kind": e.kind,
            "severity": e.severity,
            "subject": e.subject,
            "payload": json.loads(e.payload_json or "{}"),
        }
        for e in session.scalars(stmt).all()
    ]
