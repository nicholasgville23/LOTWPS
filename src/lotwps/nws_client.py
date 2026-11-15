from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class NWSError(RuntimeError):
    pass


class NWSClient:
    """Dependency-free client for the official api.weather.gov API."""

    def __init__(self, base_url: str, user_agent: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout

    def get_json(self, path_or_url: str) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("https://") else f"{self.base_url}/{path_or_url.lstrip('/')}"
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/geo+json, application/ld+json, application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise NWSError(f"NWS request failed for {url}: {exc}") from exc
        if not isinstance(data, dict):
            raise NWSError(f"Unexpected response from {url}")
        return data

    def point(self, latitude: float, longitude: float) -> dict[str, Any]:
        return self.get_json(f"points/{latitude:.4f},{longitude:.4f}")

    def active_alerts(self, latitude: float, longitude: float) -> dict[str, Any]:
        query = urllib.parse.urlencode({"point": f"{latitude:.4f},{longitude:.4f}"})
        return self.get_json(f"alerts/active?{query}")

    def forecast_from_point(self, latitude: float, longitude: float, hourly: bool = False) -> dict[str, Any]:
        point = self.point(latitude, longitude)
        key = "forecastHourly" if hourly else "forecast"
        url = point.get("properties", {}).get(key)
        if not url:
            raise NWSError(f"NWS point response does not contain {key}")
        return self.get_json(url)

    def latest_product(self, product_type: str, office: str) -> dict[str, Any] | None:
        index = self.get_json(f"products/types/{urllib.parse.quote(product_type)}/locations/{urllib.parse.quote(office)}")
        items = index.get("@graph", [])
        product_url = items[0].get("@id") if items else None
        return self.get_json(product_url) if product_url else None
