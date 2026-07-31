"""Weather via Open-Meteo — no API key, proxied and cached by the hub so the
dashboard works without the browser ever calling third parties."""

import httpx
from pydantic import BaseModel, Field

from app.widgets.base import WidgetType, register

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Injectable for tests.
transport: httpx.AsyncBaseTransport | None = None


class WeatherConfig(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    units: str = "celsius"  # celsius | fahrenheit


async def fetch_weather(config: WeatherConfig) -> dict:
    params = {
        # Rounded to ~1km so nearby configs share the cache entry.
        "latitude": round(config.lat, 2),
        "longitude": round(config.lon, 2),
        "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "forecast_days": 1,
        "timezone": "auto",
        "temperature_unit": config.units,
    }
    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()
    current = data.get("current", {})
    daily = data.get("daily", {})
    return {
        "temp": current.get("temperature_2m"),
        "weather_code": current.get("weather_code"),
        "wind_kmh": current.get("wind_speed_10m"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "temp_max": (daily.get("temperature_2m_max") or [None])[0],
        "temp_min": (daily.get("temperature_2m_min") or [None])[0],
    }


register(
    WidgetType(
        type_id="weather",
        config_model=WeatherConfig,
        fetch=fetch_weather,
        cache_ttl_s=900,
    )
)
