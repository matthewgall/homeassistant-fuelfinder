"""Config flow for Fuel Finder integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_RADIUS,
    CONF_UPDATE_INTERVAL,
    CONF_PRICE_THRESHOLD,
    CONF_FUEL_TYPE,
    DEFAULT_RADIUS,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_PRICE_THRESHOLD,
    DEFAULT_FUEL_TYPE,
    FUEL_TYPES,
    API_BASE_URL,
    API_MAPBOX_ENDPOINT,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


def _get_length_unit(hass: HomeAssistant | None) -> str:
    """Safely get the length unit string from Home Assistant."""
    if hass is None:
        return ""
    unit_system = getattr(hass.config, "unit_system", None)
    if isinstance(unit_system, str):
        return "km" if unit_system == "metric" else "mi"
    try:
        units = hass.config.units
        length = getattr(units, "length", None)
        if length is not None:
            length_str = str(length).lower()
            if "kilometer" in length_str or length_str == "km":
                return "km"
            if "mile" in length_str:
                return "mi"
        length_unit = getattr(units, "length_unit", None)
        if length_unit is not None:
            return length_unit
    except Exception:
        pass
    return ""


def _get_max_radius(hass: HomeAssistant | None) -> int:
    """Get max radius based on Home Assistant unit system."""
    radius_unit = "km" if _get_length_unit(hass) == "km" else "miles"
    return 50 if radius_unit == "km" else 31


def _validate_radius(radius: int, hass: HomeAssistant | None) -> str | None:
    """Validate radius value and return error key if invalid."""
    if not isinstance(radius, int):
        return "invalid_radius"
    max_radius = _get_max_radius(hass)
    if radius < 1:
        return "radius_too_small"
    if radius > max_radius:
        return "radius_too_large"
    return None


async def _validate_api(hass: HomeAssistant, radius: int) -> dict[str, Any]:
    """Validate fuelaround.me API by performing a test request."""
    from .coordinator import bbox_from_radius

    home_lat = hass.config.latitude
    home_lon = hass.config.longitude
    is_metric = _get_length_unit(hass) == "km"
    radius_km = radius if is_metric else radius * 1.60934

    bbox = bbox_from_radius(home_lat, home_lon, radius_km)
    center = f"{home_lon},{home_lat}"
    bbox_str = f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}"
    url = f"{API_BASE_URL}{API_MAPBOX_ENDPOINT}?bbox={bbox_str}&center={center}"

    session = async_get_clientsession(hass, verify_ssl=True)

    try:
        async with asyncio.timeout(10):
            async with session.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            ) as response:
                if response.status == 403:
                    raise CloudflareBlocked("API blocked by Cloudflare protection")
                if response.status != 200:
                    raise InvalidHost(f"HTTP {response.status}")
                json_data = await response.json()
                if "features" not in json_data:
                    raise InvalidAPIData("Missing features in response")
                if not isinstance(json_data["features"], list):
                    raise InvalidAPIData("Features is not a list")
                features = json_data["features"]
                count = len(features)
                return {
                    "title": f"Fuel Finder ({count} stations)",
                    "station_count": count,
                }
    except asyncio.TimeoutError as err:
        raise ConnectionTimeout("Timeout connecting to fuelaround.me") from err
    except aiohttp.ClientConnectorError as err:
        raise CannotConnect(f"Cannot connect to fuelaround.me: {err}") from err
    except aiohttp.ClientError as err:
        raise CannotConnect(f"Connection error: {err}") from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fuel Finder."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            radius = user_input.get(CONF_RADIUS, DEFAULT_RADIUS)

            # Manual radius validation (plain input field, not a slider)
            radius_error = _validate_radius(radius, self.hass)
            if radius_error:
                errors[CONF_RADIUS] = radius_error
            else:
                try:
                    info = await _validate_api(self.hass, radius)

                    unique_id = f"fuelfinder_{self.hass.config.latitude}_{self.hass.config.longitude}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=info["title"],
                        data=user_input,
                    )

                except ConnectionRefused:
                    errors["base"] = "connection_refused"
                except ConnectionTimeout:
                    errors["base"] = "timeout"
                except CloudflareBlocked:
                    errors["base"] = "cloudflare_blocked"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidHost:
                    errors["base"] = "invalid_host"
                except InvalidAPIData:
                    errors["base"] = "invalid_api_data"
                except Exception:
                    _LOGGER.exception("Unexpected exception during validation")
                    errors["base"] = "unknown"

        max_radius = _get_max_radius(self.hass)
        radius_unit = _get_length_unit(self.hass) or "km"

        schema = vol.Schema(
            {
                # Plain number input (not a slider) — range is validated above
                vol.Optional(CONF_RADIUS, default=DEFAULT_RADIUS): vol.Coerce(int),
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                vol.Optional(
                    CONF_PRICE_THRESHOLD, default=DEFAULT_PRICE_THRESHOLD
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=5.0)),
                vol.Optional(CONF_FUEL_TYPE, default=DEFAULT_FUEL_TYPE): vol.In(
                    FUEL_TYPES
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "radius_unit": radius_unit,
                "max_radius": str(max_radius),
            },
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Fuel Finder."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial options step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            radius = user_input.get(CONF_RADIUS, DEFAULT_RADIUS)
            radius_error = _validate_radius(radius, self.hass)
            if radius_error:
                errors[CONF_RADIUS] = radius_error
            else:
                return self.async_create_entry(title="", data=user_input)

        current_data = self._entry.data
        current_options = self._entry.options

        max_radius = _get_max_radius(self.hass)
        radius_unit = _get_length_unit(self.hass) or "km"

        current_radius = current_options.get(
            CONF_RADIUS, current_data.get(CONF_RADIUS, DEFAULT_RADIUS)
        )
        current_interval = current_options.get(
            CONF_UPDATE_INTERVAL,
            current_data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        current_threshold = current_options.get(
            CONF_PRICE_THRESHOLD,
            current_data.get(CONF_PRICE_THRESHOLD, DEFAULT_PRICE_THRESHOLD),
        )
        current_fuel_type = current_options.get(
            CONF_FUEL_TYPE,
            current_data.get(CONF_FUEL_TYPE, DEFAULT_FUEL_TYPE),
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_RADIUS, default=current_radius): vol.Coerce(int),
                vol.Optional(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=60, max=3600)
                ),
                vol.Optional(CONF_PRICE_THRESHOLD, default=current_threshold): vol.All(
                    vol.Coerce(float), vol.Range(min=0.5, max=5.0)
                ),
                vol.Optional(CONF_FUEL_TYPE, default=current_fuel_type): vol.In(
                    FUEL_TYPES
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "radius_unit": radius_unit,
                "max_radius": str(max_radius),
            },
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class ConnectionRefused(Exception):
    """Error to indicate the connection was actively refused."""


class ConnectionTimeout(Exception):
    """Error to indicate the connection timed out."""


class InvalidHost(Exception):
    """Error to indicate there is an invalid response."""


class InvalidAPIData(Exception):
    """Error to indicate invalid API data format."""


class CloudflareBlocked(Exception):
    """Error to indicate Cloudflare blocked the request."""
