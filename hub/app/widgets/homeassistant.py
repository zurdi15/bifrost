"""Home Assistant entities via its REST API (long-lived access token) —
proxied and cached by the hub like every widget, so the browser never talks
to HA directly. The token lives in the widget config inside bifrost.db; the
dashboard's threat model is network-layer by design (see architecture docs).
"""

import httpx
from pydantic import BaseModel, Field

from app.widgets.base import WidgetType, register

# Injectable for tests.
transport: httpx.AsyncBaseTransport | None = None


class HAConfig(BaseModel):
    base_url: str = "http://homeassistant:8123"
    token: str = ""
    # Entity ids to display, in order (e.g. sensor.processor_use).
    entities: list[str] = Field(default_factory=list, max_length=20)


async def fetch_ha(config: HAConfig) -> dict:
    if not config.token or not config.entities:
        return {"configured": False, "entities": []}
    headers = {"Authorization": f"Bearer {config.token}"}
    async with httpx.AsyncClient(timeout=10, transport=transport, headers=headers) as client:
        # One /api/states call filtered locally beats N per-entity requests.
        response = await client.get(f"{config.base_url.rstrip('/')}/api/states")
        response.raise_for_status()
        states = {s.get("entity_id"): s for s in response.json()}

    entities = []
    for entity_id in config.entities:
        state = states.get(entity_id)
        attributes = (state or {}).get("attributes", {})
        entities.append(
            {
                "entity_id": entity_id,
                "name": attributes.get("friendly_name") or entity_id,
                "state": (state or {}).get("state"),
                "unit": attributes.get("unit_of_measurement"),
            }
        )
    return {"configured": True, "entities": entities}


register(
    WidgetType(
        type_id="homeassistant",
        config_model=HAConfig,
        fetch=fetch_ha,
        cache_ttl_s=30,
    )
)
