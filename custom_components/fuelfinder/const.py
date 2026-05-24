"""Constants for Fuel Finder integration."""

import json
import os

# Load version from manifest.json so the User-Agent stays in sync
# with HACS releases automatically.
_manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
with open(_manifest_path) as _manifest_file:
    _manifest = json.load(_manifest_file)

INTEGRATION_VERSION = _manifest.get("version", "unknown")

DOMAIN = "fuelfinder"

# Configuration keys
CONF_RADIUS = "radius"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_PRICE_THRESHOLD = "price_threshold"
CONF_FUEL_TYPE = "fuel_type"

# Sensor types
SENSOR_CHEAPEST = "cheapest"
SENSOR_STATIONS_COUNT = "stations_count"
SENSOR_NEARBY_STATIONS = "nearby_stations"
SENSOR_AVERAGE_PRICE = "average_price"
SENSOR_BEST_DISTANCE = "best_distance"

# Default values
DEFAULT_RADIUS = 10
DEFAULT_UPDATE_INTERVAL = 600
DEFAULT_PRICE_THRESHOLD = 1.40
DEFAULT_FUEL_TYPE = "any"

# Fuel types
FUEL_TYPE_ANY = "any"
FUEL_TYPE_UNLEADED = "unleaded"
FUEL_TYPE_DIESEL = "diesel"
FUEL_TYPE_PREMIUM = "premium"

FUEL_TYPES = {
    FUEL_TYPE_ANY: "Any fuel",
    FUEL_TYPE_UNLEADED: "Unleaded petrol",
    FUEL_TYPE_DIESEL: "Diesel",
    FUEL_TYPE_PREMIUM: "Premium / Super",
}

# API settings
API_BASE_URL = "https://fuelaround.me"
API_MAPBOX_ENDPOINT = "/api/data.mapbox"
API_STATION_ENDPOINT = "/api/station"

# Retry settings
MAX_RETRIES = 2
RETRY_BACKOFF = [5, 15]
DEFAULT_TIMEOUT = 30

# User-Agent for all API requests to fuelaround.me
# Please whitelist this exact string on your edge/WAF if needed.
# The version is pulled from manifest.json automatically on every HACS release.
USER_AGENT = (
    f"HomeAssistant-FuelFinder/{INTEGRATION_VERSION} "
    f"(+https://github.com/matthewgall/homeassistant-fuelfinder)"
)

# Conversion
EARTH_RADIUS_KM = 6371.0
KM_PER_DEGREE_LAT = 111.0
