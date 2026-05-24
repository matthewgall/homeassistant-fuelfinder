"""Data update coordinator for Fuel Finder."""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_RADIUS,
    CONF_UPDATE_INTERVAL,
    CONF_FUEL_TYPE,
    DEFAULT_RADIUS,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_FUEL_TYPE,
    FUEL_TYPES,
    MAX_RETRIES,
    RETRY_BACKOFF,
    DEFAULT_TIMEOUT,
    API_BASE_URL,
    API_MAPBOX_ENDPOINT,
    EARTH_RADIUS_KM,
    KM_PER_DEGREE_LAT,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in km."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def bbox_from_radius(lat: float, lon: float, radius_km: float) -> dict[str, float]:
    """Calculate a bounding box from a center point and radius in km."""
    # Approximate degrees per km
    lat_delta = radius_km / KM_PER_DEGREE_LAT
    lon_delta = radius_km / (KM_PER_DEGREE_LAT * math.cos(math.radians(lat)))

    return {
        "west": max(lon - lon_delta, -180.0),
        "south": max(lat - lat_delta, -90.0),
        "east": min(lon + lon_delta, 180.0),
        "north": min(lat + lat_delta, 90.0),
    }


class FuelDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching fuel station data from fuelaround.me."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        self.config_entry = config_entry

        update_interval = timedelta(
            seconds=self._get_config_value(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            )
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    def _get_config_value(self, key: str, default: Any) -> Any:
        """Return a config value, preferring options over data."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )

    @property
    def radius(self) -> int:
        """Return the configured radius."""
        return self._get_config_value(CONF_RADIUS, DEFAULT_RADIUS)

    @property
    def fuel_type(self) -> str:
        """Return the configured fuel type."""
        return self._get_config_value(CONF_FUEL_TYPE, DEFAULT_FUEL_TYPE)

    @property
    def home_location(self) -> tuple[float, float]:
        """Return the Home Assistant configured home location."""
        return (self.hass.config.latitude, self.hass.config.longitude)

    @property
    def is_metric(self) -> bool:
        """Return True if Home Assistant uses metric units."""
        units = self.hass.config.units
        length_unit = getattr(units, "length_unit", getattr(units, "length", ""))
        return length_unit == "km"

    def _radius_km(self) -> float:
        """Return the configured radius in kilometres."""
        return self.radius if self.is_metric else self.radius * 1.60934

    def format_distance(self, km: float | None) -> str:
        """Format distance with appropriate unit."""
        if km is None:
            return "Unknown"
        if self.is_metric:
            return f"{km:.1f} km"
        return f"{km / 1.60934:.1f} mi"

    @property
    def url(self) -> str:
        """Return the API URL being queried."""
        return f"{API_BASE_URL}{API_MAPBOX_ENDPOINT}"

    async def _async_fetch_data(self, url: str) -> dict[str, Any]:
        """Fetch data from URL with retry logic."""
        session = async_get_clientsession(self.hass, verify_ssl=True)

        last_error: Exception | None = None
        retry_delay: int | None = None

        for attempt in range(MAX_RETRIES + 1):
            retry_delay = None
            try:
                async with asyncio.timeout(DEFAULT_TIMEOUT):
                    async with session.get(
                        url,
                        headers={
                            "User-Agent": USER_AGENT,
                            "Accept": "application/json",
                        },
                    ) as response:
                        if response.status == 200:
                            return await response.json()

                        if 400 <= response.status < 500:
                            raise UpdateFailed(
                                f"Error fetching fuel data: HTTP {response.status}"
                            )

                        last_error = aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                        )
                        if attempt < MAX_RETRIES:
                            _LOGGER.warning(
                                "Server error %d from fuelaround.me (attempt %d/%d), retrying in %ds",
                                response.status,
                                attempt + 1,
                                MAX_RETRIES + 1,
                                RETRY_BACKOFF[attempt],
                            )
                            retry_delay = RETRY_BACKOFF[attempt]

            except asyncio.TimeoutError as err:
                last_error = err
                if attempt < MAX_RETRIES:
                    _LOGGER.warning(
                        "Timeout fetching fuel data (attempt %d/%d), retrying in %ds",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        RETRY_BACKOFF[attempt],
                    )
                    retry_delay = RETRY_BACKOFF[attempt]
                else:
                    raise UpdateFailed(
                        "Timeout fetching fuel data from fuelaround.me"
                    ) from err

            except aiohttp.ClientError as err:
                last_error = err
                if attempt < MAX_RETRIES:
                    _LOGGER.warning(
                        "Connection error from fuelaround.me (attempt %d/%d): %s, retrying in %ds",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        err,
                        RETRY_BACKOFF[attempt],
                    )
                    retry_delay = RETRY_BACKOFF[attempt]
                else:
                    raise UpdateFailed(
                        f"Error fetching fuel data from fuelaround.me: {err}"
                    ) from err

            if retry_delay is not None:
                await asyncio.sleep(retry_delay)

        if last_error is not None:
            raise UpdateFailed(
                f"Error fetching fuel data from fuelaround.me: {last_error}"
            )

        raise UpdateFailed("Unexpected error in fetch retry logic")

    def _extract_fuel_price(
        self, props: dict[str, Any]
    ) -> tuple[float | None, dict[str, float]]:
        """Extract the price for the configured fuel type.

        Returns (price_for_selected_fuel, all_grouped_fuels).
        """
        grouped_fuels: dict[str, Any] = props.get("grouped_fuels", {})
        parsed_fuels: dict[str, float] = {}

        for key, value in grouped_fuels.items():
            try:
                parsed_fuels[key] = float(value)
            except (TypeError, ValueError):
                continue

        fuel_type = self.fuel_type
        if fuel_type == "any" or fuel_type not in parsed_fuels:
            # Fall back to the overall lowest price
            lowest = props.get("lowest_price")
            try:
                return (float(lowest) if lowest is not None else None), parsed_fuels
            except (TypeError, ValueError):
                return None, parsed_fuels

        return parsed_fuels.get(fuel_type), parsed_fuels

    def _process_station(
        self, feature: dict[str, Any], home_lat: float, home_lon: float
    ) -> dict[str, Any] | None:
        """Process a single GeoJSON feature into station data."""
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        coords = geometry.get("coordinates", [None, None])

        if len(coords) < 2 or coords[0] is None or coords[1] is None:
            return None

        lon, lat = coords[0], coords[1]
        distance_km = haversine_distance(home_lat, home_lon, lat, lon)

        fuel_price, grouped_fuels = self._extract_fuel_price(props)

        result: dict[str, Any] = {
            "station_id": props.get("station_id"),
            "brand": props.get("brand", "Unknown"),
            "title": props.get("title", "Unknown Station"),
            "postcode": props.get("postcode", ""),
            "latitude": lat,
            "longitude": lon,
            "distance_km": round(distance_km, 2),
            "distance_display": self.format_distance(distance_km),
            "has_prices": props.get("has_prices", False),
            "data_issue": props.get("data_issue", False),
            "grouped_fuels": grouped_fuels,
        }

        if fuel_price is not None:
            result["lowest_price"] = round(fuel_price, 2)
            result["price_display"] = f"£{fuel_price:.2f}"

        if props.get("is_best_price"):
            result["is_best_price"] = True

        return result

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch fuel station data from fuelaround.me."""
        home_lat, home_lon = self.home_location
        radius_km = self._radius_km()

        bbox = bbox_from_radius(home_lat, home_lon, radius_km)
        center = f"{home_lon},{home_lat}"
        bbox_str = f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}"
        url = f"{self.url}?bbox={bbox_str}&center={center}"

        data = await self._async_fetch_data(url)

        if not isinstance(data, dict) or "features" not in data or not isinstance(data["features"], list):
            raise UpdateFailed("Invalid fuel data: missing features array")

        stations = []
        for feature in data["features"]:
            station = self._process_station(feature, home_lat, home_lon)
            if station is not None:
                # Only include stations within the actual radius (bbox is approximate)
                if station["distance_km"] <= radius_km:
                    stations.append(station)

        # Sort by lowest price first, then by distance
        stations.sort(key=lambda x: (x.get("lowest_price", float("inf")), x["distance_km"]))

        # Calculate statistics
        prices = [s["lowest_price"] for s in stations if "lowest_price" in s]
        avg_price = sum(prices) / len(prices) if prices else None
        best_price = min(prices) if prices else None
        best_station = next(
            (s for s in stations if s.get("lowest_price") == best_price), None
        )

        return {
            "stations": stations,
            "station_count": len(stations),
            "average_price": round(avg_price, 2) if avg_price else None,
            "best_price": round(best_price, 2) if best_price else None,
            "best_station": best_station,
            "home_latitude": home_lat,
            "home_longitude": home_lon,
            "radius_km": radius_km,
            "fuel_type": self.fuel_type,
            "fuel_type_label": FUEL_TYPES.get(self.fuel_type, self.fuel_type),
            "last_update": data.get("timestamp") if isinstance(data, dict) else None,
        }
