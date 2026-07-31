"""Clock is rendered entirely in the frontend; the hub only stores its config."""

from pydantic import BaseModel

from app.widgets.base import WidgetType, register


class ClockConfig(BaseModel):
    show_seconds: bool = True
    timezone: str | None = None


register(WidgetType(type_id="clock", config_model=ClockConfig))
