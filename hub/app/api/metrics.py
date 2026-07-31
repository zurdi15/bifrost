import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.db import session_scope
from app.metrics.store import MetricsStore
from app.models import Node, now_ts

router = APIRouter()


@router.get("/metrics")
async def query_metrics(
    request: Request,
    node: str = Query(description="node uuid"),
    m: str = Query(description="comma-separated metric names"),
    from_ts: int | None = Query(default=None, alias="from"),
    to_ts: int | None = Query(default=None, alias="to"),
) -> dict:
    store: MetricsStore = request.app.state.metrics
    with session_scope() as session:
        node_row = session.scalar(select(Node).where(Node.uuid == node))
        if node_row is None:
            raise HTTPException(status_code=404, detail="node not found")
        node_id = node_row.id

    to_ts = to_ts or now_ts()
    from_ts = from_ts or to_ts - 3600
    names = [name.strip() for name in m.split(",") if name.strip()]
    if not names:
        raise HTTPException(status_code=422, detail="no metric names given")

    series = await asyncio.to_thread(store.query_sync, node_id, names, from_ts, to_ts)
    return {
        "node": node,
        "from": from_ts,
        "to": to_ts,
        "res": "raw",
        "series": {name: [[ts, value] for ts, value in points] for name, points in series.items()},
    }
