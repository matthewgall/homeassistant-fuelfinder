"""Binary sensors for Fuel Finder integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
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
    """Set up Fuel Finder binary sensors from config entry."""
    coordinator: FuelDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = [
        FuelStationsAvailableBinarySensor(coordinator, config_entry),
        FuelLowPriceBinarySensor(coordinator, config_entry),
        FuelBestPriceNearbyBinarySensor(coordinator, config_entry),
    ]

    async_add_entities(entities)


class FuelBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for Fuel Finder binary sensors."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the binary sensor."""
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


class FuelStationsAvailableBinarySensor(FuelBinarySensorBase):
    """Binary sensor indicating fuel stations are in range."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize stations available sensor."""
        super().__init__(coordinator, config_entry, "stations_available")
        self._attr_name = "Stations Available"
        self._attr_icon = "mdi:gas-station"
        self._attr_device_class = None

    @property
    def is_on(self) -> bool:
        """Return True if stations are in range."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("station_count", 0) > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if not self.coordinator.data:
            return {"status": "No data"}

        return {
            "station_count": self.coordinator.data.get("station_count", 0),
            "radius_km": round(self.coordinator.data.get("radius_km", 0), 1),
        }


class FuelLowPriceBinarySensor(FuelBinarySensorBase):
    """Binary sensor indicating cheap fuel is available."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize low price sensor."""
        super().__init__(coordinator, config_entry, "low_price_available")
        self._attr_name = "Low Price Available"
        self._attr_icon = "mdi:tag-check"
        self._attr_device_class = None

    @property
    def is_on(self) -> bool:
        """Return True if fuel below threshold is available."""
        if not self.coordinator.data:
            return False

        best_price = self.coordinator.data.get("best_price")
        if best_price is None:
            return False

        threshold = self._get_config_value(CONF_PRICE_THRESHOLD, DEFAULT_PRICE_THRESHOLD)
        return best_price < threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return low price details."""
        if not self.coordinator.data:
            return {"status": "No data"}

        best_price = self.coordinator.data.get("best_price")
        threshold = self._get_config_value(CONF_PRICE_THRESHOLD, DEFAULT_PRICE_THRESHOLD)
        best_station = self.coordinator.data.get("best_station", {})

        return {
            "best_price": best_price,
            "price_threshold": threshold,
            "price_difference": (
                round(threshold - best_price, 2)
                if best_price is not None
                else None
            ),
            "station": best_station.get("brand", "Unknown"),
            "postcode": best_station.get("postcode", ""),
            "distance": best_station.get("distance_display", "Unknown"),
        }


class FuelBestPriceNearbyBinarySensor(FuelBinarySensorBase):
    """Binary sensor indicating a best-price station is nearby."""

    def __init__(
        self,
        coordinator: FuelDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize best price nearby sensor."""
        super().__init__(coordinator, config_entry, "best_price_nearby")
        self._attr_name = "Best Price Nearby"
        self._attr_icon = "mdi:trophy"
        self._attr_device_class = None

    @property
    def is_on(self) -> bool:
        """Return True if a station flagged as best price is in range."""
        if not self.coordinator.data:
            return False

        stations = self.coordinator.data.get("stations", [])
        return any(s.get("is_best_price") for s in stations)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return best price stations."""
        if not self.coordinator.data:
            return {"status": "No data"}

        stations = self.coordinator.data.get("stations", [])
        best_price_stations = [s for s in stations if s.get("is_best_price")]

        return {
            "best_price_count": len(best_price_stations),
            "best_price_stations": best_price_stations,
        }
