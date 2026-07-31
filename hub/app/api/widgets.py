import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session, session_scope
from app.models import Dashboard, Widget

# Importing the package registers the built-in widget types.
from app.widgets import clock as _clock  # noqa: F401
from app.widgets import weather as _weather  # noqa: F401
from app.widgets.base import REGISTRY

router = APIRouter()

DEFAULT_DASHBOARD = "default"


def _widget_to_dict(widget: Widget) -> dict:
    return {
        "id": widget.id,
        "type": widget.type,
        "title": widget.title,
        "config": json.loads(widget.config_json or "{}"),
        "enabled": widget.enabled,
    }


@router.get("/widgets")
def list_widgets(session: Session = Depends(get_session)) -> list[dict]:
    return [_widget_to_dict(w) for w in session.scalars(select(Widget).order_by(Widget.id))]


class WidgetCreate(BaseModel):
    type: str
    title: str | None = None
    config: dict = {}


@router.post("/widgets", status_code=201)
def create_widget(body: WidgetCreate, session: Session = Depends(get_session)) -> dict:
    widget_type = REGISTRY.get(body.type)
    if widget_type is None:
        raise HTTPException(status_code=422, detail=f"unknown widget type {body.type}")
    try:
        config = widget_type.config_model.model_validate(body.config)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    widget = Widget(type=body.type, title=body.title, config_json=config.model_dump_json())
    session.add(widget)
    session.flush()
    return _widget_to_dict(widget)


class WidgetPatch(BaseModel):
    title: str | None = None
    config: dict | None = None
    enabled: bool | None = None


@router.patch("/widgets/{widget_id}")
def patch_widget(
    widget_id: int, body: WidgetPatch, session: Session = Depends(get_session)
) -> dict:
    widget = session.get(Widget, widget_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="widget not found")
    if body.title is not None:
        widget.title = body.title
    if body.enabled is not None:
        widget.enabled = body.enabled
    if body.config is not None:
        widget_type = REGISTRY.get(widget.type)
        if widget_type is None:
            raise HTTPException(status_code=422, detail="orphan widget type")
        try:
            config = widget_type.config_model.model_validate(body.config)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        widget.config_json = config.model_dump_json()
    session.flush()
    return _widget_to_dict(widget)


@router.delete("/widgets/{widget_id}", status_code=204)
def delete_widget(widget_id: int, session: Session = Depends(get_session)) -> None:
    widget = session.get(Widget, widget_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="widget not found")
    session.delete(widget)


@router.get("/widgets/{widget_id}/data")
async def widget_data(widget_id: int) -> dict:
    with session_scope() as session:
        widget = session.get(Widget, widget_id)
        if widget is None:
            raise HTTPException(status_code=404, detail="widget not found")
        widget_type = REGISTRY.get(widget.type)
        if widget_type is None:
            raise HTTPException(status_code=422, detail="orphan widget type")
        config = json.loads(widget.config_json or "{}")
    try:
        data = await widget_type.data(config)
    except Exception as exc:  # third-party fetch failed
        raise HTTPException(status_code=502, detail=f"widget fetch failed: {exc}") from exc
    return {"id": widget_id, "type": widget.type, "data": data}


@router.get("/dashboard")
def get_dashboard(session: Session = Depends(get_session)) -> dict:
    dashboard = session.scalar(select(Dashboard).where(Dashboard.name == DEFAULT_DASHBOARD))
    return json.loads(dashboard.layout_json) if dashboard else {}


@router.put("/dashboard")
def put_dashboard(layout: dict, session: Session = Depends(get_session)) -> dict:
    dashboard = session.scalar(select(Dashboard).where(Dashboard.name == DEFAULT_DASHBOARD))
    if dashboard is None:
        dashboard = Dashboard(name=DEFAULT_DASHBOARD)
        session.add(dashboard)
    dashboard.layout_json = json.dumps(layout)
    session.flush()
    return layout
