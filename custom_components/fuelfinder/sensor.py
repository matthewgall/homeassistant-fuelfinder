"""Sensors for Fuel Finder integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_CHEAPEST,
    SENSOR_STATIONS_COUNT,
    SENSOR_NEARBY_STATIONS,
    SENSOR_AVERAGE_PRICE,
    SENSOR_BEST_DISTANCE,
    CONF_PRICE_THRESHOLD,
    CONF_FUEL_TYPE,
    DEFAULT_PRICE_THRESHOLD,
    DEFAULT_FUEL_TYPE,
    FUEL_TYPES,
)
from .coordinator import FuelDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fuel Finder sensors from config entry."""
    coordinator: FuelDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = [
        FuelCheapestSensor(coordinator, config_entry),
        FuelStationsCountSensor(coordinator, config_entry),
        FuelNearbyStationsSensor(coordinator, config_entry),
        FuelAveragePriceSensor(coordinator, config_entry),
        FuelBestDistanceSensor(coordinator, config_entry),
    ]

    async_add_entities(entities)


class FuelSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Fuel Finder sensors."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.sensor_type = sensor_type

        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"
        fuel_type = self._get_config_value(CONF_FUEL_TYPE, DEFAULT_FUEL_TYPE)
        fuel_label = FUEL_TYPES.get(fuel_type, fuel_type)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name="Fuel Finder",
            manufacturer="Matthew Gall",
            model=f"Fuel Price Tracker ({fuel_label})",
            configuration_url="https://fuelaround.me",
        )

    def _get_config_value(self, key: str, default: Any) -> Any:
        """Return a config value, preferring options over data."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )


class FuelCheapestSensor(FuelSensorBase):
    """Sensor for the cheapest fuel station."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize cheapest fuel sensor."""
        super().__init__(coordinator, config_entry, SENSOR_CHEAPEST)
        self._attr_name = "Cheapest Fuel"
        self._attr_icon = "mdi:gas-station"

    @property
    def native_value(self) -> str | None:
        """Return the cheapest station name and price."""
        best = self._get_best_station()
        if not best:
            return "No stations"
        price = best.get("lowest_price")
        brand = best.get("brand", "Unknown")
        fuel_label = self.coordinator.data.get("fuel_type_label", "") if self.coordinator.data else ""
        if price is not None:
            if fuel_label and fuel_label != "Any fuel":
                return f"{brand} £{price:.2f} ({fuel_label})"
            return f"{brand} £{price:.2f}"
        return brand

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return cheapest station details as attributes."""
        best = self._get_best_station()
        if not best:
            return {"status": "No stations in range"}

        attrs = dict(best)
        # Add the price threshold for reference
        threshold = self._get_config_value(CONF_PRICE_THRESHOLD, DEFAULT_PRICE_THRESHOLD)
        attrs["price_threshold"] = threshold
        attrs["below_threshold"] = (
            best.get("lowest_price", float("inf")) < threshold
            if best.get("lowest_price") is not None
            else False
        )
        # Add fuel type context
        if self.coordinator.data:
            attrs["fuel_type"] = self.coordinator.data.get("fuel_type")
            attrs["fuel_type_label"] = self.coordinator.data.get("fuel_type_label")
        return attrs

    def _get_best_station(self) -> dict[str, Any] | None:
        """Get the best priced station from coordinator data."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("best_station")


class FuelStationsCountSensor(FuelSensorBase):
    """Sensor for total stations in range."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize stations count sensor."""
        super().__init__(coordinator, config_entry, SENSOR_STATIONS_COUNT)
        self._attr_name = "Stations in Range"
        self._attr_icon = "mdi:map-marker-multiple"
        self._attr_native_unit_of_measurement = "stations"

    @property
    def native_value(self) -> int | None:
        """Return the number of stations in range."""
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.get("station_count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes including full station list."""
        if not self.coordinator.data:
            return {"status": "No data"}

        stations = self.coordinator.data.get("stations", [])
        prices = [s["lowest_price"] for s in stations if "lowest_price" in s]

        attrs = {
            "home_latitude": self.coordinator.data.get("home_latitude"),
            "home_longitude": self.coordinator.data.get("home_longitude"),
            "radius_km": round(self.coordinator.data.get("radius_km", 0), 1),
            "average_price": self.coordinator.data.get("average_price"),
            "best_price": self.coordinator.data.get("best_price"),
            "stations_with_prices": len(prices),
            "stations_without_prices": len(stations) - len(prices),
            "fuel_type": self.coordinator.data.get("fuel_type"),
            "fuel_type_label": self.coordinator.data.get("fuel_type_label"),
        }

        # Add top 10 stations as individual attributes for easy scripting
        for i, station in enumerate(stations[:10], 1):
            attrs[f"station_{i}"] = station

        # Also provide the full list as a single attribute for template use
        attrs["all_stations"] = stations

        return attrs


class FuelNearbyStationsSensor(FuelSensorBase):
    """Sensor showing nearby stations summary."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize nearby stations sensor."""
        super().__init__(coordinator, config_entry, SENSOR_NEARBY_STATIONS)
        self._attr_name = "Nearby Stations"
        self._attr_icon = "mdi:format-list-bulleted"

    @property
    def native_value(self) -> str | None:
        """Return summary of nearby stations."""
        if not self.coordinator.data:
            return "No data"

        stations = self.coordinator.data.get("stations", [])
        count = len(stations)
        best_price = self.coordinator.data.get("best_price")

        if count == 0:
            return "No stations in range"
        if best_price:
            return f"{count} stations, best £{best_price:.2f}"
        return f"{count} stations"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return structured station data for automations."""
        if not self.coordinator.data:
            return {"status": "No data"}

        stations = self.coordinator.data.get("stations", [])
        attrs: dict[str, Any] = {}

        # Fuel type context
        attrs["fuel_type"] = self.coordinator.data.get("fuel_type")
        attrs["fuel_type_label"] = self.coordinator.data.get("fuel_type_label")

        # Provide stations grouped by brand for easy filtering
        by_brand: dict[str, list[dict[str, Any]]] = {}
        for station in stations:
            brand = station.get("brand", "Unknown")
            by_brand.setdefault(brand, []).append(station)

        attrs["stations_by_brand"] = by_brand
        attrs["brand_count"] = len(by_brand)

        # Cheapest station per brand
        cheapest_by_brand = {}
        for brand, brand_stations in by_brand.items():
            priced = [s for s in brand_stations if "lowest_price" in s]
            if priced:
                cheapest = min(priced, key=lambda x: x["lowest_price"])
                cheapest_by_brand[brand] = cheapest
        attrs["cheapest_by_brand"] = cheapest_by_brand

        return attrs


class FuelAveragePriceSensor(FuelSensorBase):
    """Sensor for average fuel price in range."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize average price sensor."""
        super().__init__(coordinator, config_entry, SENSOR_AVERAGE_PRICE)
        self._attr_name = "Average Fuel Price"
        self._attr_icon = "mdi:cash-multiple"
        self._attr_native_unit_of_measurement = "GBP"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return the average fuel price."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("average_price")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return price statistics."""
        if not self.coordinator.data:
            return {"status": "No data"}

        stations = self.coordinator.data.get("stations", [])
        prices = [s["lowest_price"] for s in stations if "lowest_price" in s]

        if not prices:
            return {"status": "No price data"}

        return {
            "fuel_type": self.coordinator.data.get("fuel_type"),
            "fuel_type_label": self.coordinator.data.get("fuel_type_label"),
            "min_price": min(prices),
            "max_price": max(prices),
            "average_price": self.coordinator.data.get("average_price"),
            "price_count": len(prices),
            "price_range": round(max(prices) - min(prices), 2),
        }


class FuelBestDistanceSensor(FuelSensorBase):
    """Sensor for distance to the cheapest station."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize best distance sensor."""
        super().__init__(coordinator, config_entry, SENSOR_BEST_DISTANCE)
        self._attr_name = "Distance to Cheapest"
        self._attr_icon = "mdi:map-marker-distance"

    @property
    def native_value(self) -> str | None:
        """Return distance to the cheapest station."""
        best = self._get_best_station()
        if not best:
            return "Unknown"
        return best.get("distance_display", "Unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return distance details."""
        best = self._get_best_station()
        if not best:
            return {"status": "No stations in range"}

        return {
            "distance_km": best.get("distance_km"),
            "latitude": best.get("latitude"),
            "longitude": best.get("longitude"),
            "station_id": best.get("station_id"),
            "brand": best.get("brand"),
            "postcode": best.get("postcode"),
        }

    def _get_best_station(self) -> dict[str, Any] | None:
        """Get the best priced station from coordinator data."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("best_station")
