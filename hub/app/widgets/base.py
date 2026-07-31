"""Widget type registry.

A widget type declares its config schema and (optionally) a server-side fetch
with caching — the browser never talks to third parties directly. Adding a
widget type = one module in this package registering itself; the API layer
dispatches by type with zero changes.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class WidgetType:
    type_id: str
    config_model: type[BaseModel]
    # fetch(config) -> payload; None for frontend-only widgets (clock).
    fetch: Callable[[BaseModel], Awaitable[dict]] | None = None
    cache_ttl_s: int = 0
    _cache: dict[str, tuple[float, dict]] = field(default_factory=dict)

    async def data(self, raw_config: dict) -> dict | None:
        if self.fetch is None:
            return None
        config = self.config_model.model_validate(raw_config)
        key = config.model_dump_json()
        if self.cache_ttl_s:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < self.cache_ttl_s:
                return cached[1]
        payload = await self.fetch(config)
        if self.cache_ttl_s:
            self._cache[key] = (time.monotonic(), payload)
        return payload


REGISTRY: dict[str, WidgetType] = {}


def register(widget_type: WidgetType) -> WidgetType:
    REGISTRY[widget_type.type_id] = widget_type
    return widget_type
