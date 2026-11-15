"""Small, cache-friendly client for the public National Weather Service API.

The service uses official NWS point metadata to discover the correct forecast grid.
It never fabricates a forecast when the API is unavailable.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import Station, WeatherAlert, sort_alerts

API_ROOT = "https://api.weather.gov"


class NWSAPIError(RuntimeError):
    """Raised when an NWS API request cannot be completed."""


class NWSClient:
    def __init__(self, user_agent: str, timeout: float = 15.0) -> None:
        if not user_agent.strip():
            raise ValueError("An informative NWS User-Agent is required")
        self.user_agent = user_agent
        self.timeout = timeout

    def _get_json(self, url: str) -> dict[str, Any]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/geo+json, application/ld+json, application/json",
        }
        last_error: Exception | None = None
        for attempt in range(3):
            request = Request(url, headers=headers)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise NWSAPIError(f"Unexpected response shape from {url}")
                return value
            except HTTPError as exc:
                last_error = exc
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise NWSAPIError(f"NWS API returned HTTP {exc.code} for {url}") from exc
            except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                last_error = exc
                if attempt == 2:
                    raise NWSAPIError(f"NWS API request failed for {url}: {exc}") from exc
            time.sleep(1.0 + attempt)
        raise NWSAPIError(f"NWS API request failed: {last_error}")

    def get_point(self, station: Station) -> dict[str, Any]:
        return self._get_json(
            f"{API_ROOT}/points/{station.latitude:.4f},{station.longitude:.4f}"
        )

    def get_active_alerts(self, station: Station) -> list[WeatherAlert]:
        url = (
            f"{API_ROOT}/alerts/active?point="
            f"{station.latitude:.4f}%2C{station.longitude:.4f}"
        )
        payload = self._get_json(url)
        features = payload.get("features") or []
        alerts = [WeatherAlert.from_feature(item) for item in features if isinstance(item, dict)]
        return sort_alerts(alerts)

    def get_forecast(self, station: Station, hourly: bool = False) -> list[dict[str, Any]]:
        point = self.get_point(station)
        properties = point.get("properties") or {}
        forecast_url = properties.get("forecastHourly" if hourly else "forecast")
        if not forecast_url:
            raise NWSAPIError(f"No {'hourly ' if hourly else ''}forecast grid is available for {station.station_id}")
        forecast = self._get_json(str(forecast_url))
        forecast_properties = forecast.get("properties") or {}
        return [
            item for item in (forecast_properties.get("periods") or [])
            if isinstance(item, dict)
        ]

    def get_observation(self, station: Station) -> dict[str, Any] | None:
        point = self.get_point(station)
        properties = point.get("properties") or {}
        stations_url = properties.get("observationStations")
        if not stations_url:
            return None
        stations_payload = self._get_json(str(stations_url))
        features = stations_payload.get("features") or []
        if not features:
            return None
        station_props = (features[0] or {}).get("properties") or {}
        station_id = station_props.get("stationIdentifier")
        if not station_id:
            return None
        latest = self._get_json(f"{API_ROOT}/stations/{quote(str(station_id))}/observations/latest")
        return latest.get("properties") or None

    def get_latest_text_product(self, office: str, product_type: str) -> str | None:
        """Retrieve the latest text product, e.g. HWO or CLI, when published."""
        office = office.upper().strip()
        product_type = product_type.upper().strip()
        if not office.isalnum() or len(office) != 3 or not product_type.isalnum():
            raise ValueError("Invalid NWS office or product type")
        index = self._get_json(
            f"{API_ROOT}/products/types/{quote(product_type)}/locations/{quote(office)}"
        )
        products = index.get("@graph") or index.get("products") or []
        if not products:
            return None
        product_id = products[0].get("id") if isinstance(products[0], dict) else None
        if not product_id:
            return None
        product = self._get_json(f"{API_ROOT}/products/{quote(str(product_id))}")
        return str(product.get("productText") or "") or None

    def fetch_station(self, station: Station) -> dict[str, Any]:
        """Fetch point metadata, forecasts, current alerts and latest observation."""
        point = self.get_point(station)
        properties = point.get("properties") or {}
        forecast_url = properties.get("forecast")
        hourly_url = properties.get("forecastHourly")
        forecast = self._get_json(str(forecast_url)) if forecast_url else {}
        hourly = self._get_json(str(hourly_url)) if hourly_url else {}
        alerts_payload = self._get_json(
            f"{API_ROOT}/alerts/active?point={station.latitude:.4f}%2C{station.longitude:.4f}"
        )
        observation: dict[str, Any] | None = None
        stations_url = properties.get("observationStations")
        if stations_url:
            stations_payload = self._get_json(str(stations_url))
            features = stations_payload.get("features") or []
            if features:
                station_props = (features[0] or {}).get("properties") or {}
                observation_id = station_props.get("stationIdentifier")
                if observation_id:
                    latest = self._get_json(
                        f"{API_ROOT}/stations/{quote(str(observation_id))}/observations/latest"
                    )
                    observation = latest.get("properties") or None

        forecast_periods = ((forecast.get("properties") or {}).get("periods") or [])
        hourly_periods = ((hourly.get("properties") or {}).get("periods") or [])
        alerts = [
            WeatherAlert.from_feature(feature)
            for feature in (alerts_payload.get("features") or [])
            if isinstance(feature, dict)
        ]
        office_url = properties.get("forecastOffice") or ""
        office = str(office_url).rstrip("/").split("/")[-1] if office_url else "LOT"
        return {
            "point": properties,
            "office": office,
            "forecast_periods": forecast_periods,
            "hourly_periods": hourly_periods,
            "alerts": sort_alerts(alerts),
            "observation": observation,
        }
