# Fuel Finder

A Home Assistant custom integration that monitors fuel prices from [fuelaround.me](https://fuelaround.me) and shows petrol stations within a specified radius of your Home Assistant home location.

## Features

- **Live fuel price tracking** from fuelaround.me (UK fuel stations)
- **Radius-based filtering** — show stations within a configurable distance of your home
- **Rich sensor data** including cheapest station, average price, station count, and distances
- **Binary sensors** for automations: stations available, low price alerts, best price nearby
- **Full station list in attributes** for template scripting and advanced automations
- **Price threshold** configuration to trigger automations when cheap fuel is available
- Supports both **metric (km)** and **imperial (miles)** units based on your Home Assistant settings

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Custom repositories**
3. Add `https://github.com/matthewgall/homeassistant-fuelfinder` and select **Integration** as the category
4. Click **Install**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/fuelfinder/` directory to your Home Assistant `custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings > Devices & Services**
2. Click **Add Integration**
3. Search for **Fuel Finder**
4. Configure the following options:

| Option | Description | Default |
|--------|-------------|---------|
| Search Radius | Maximum distance from your home location | 10 km / miles |
| Update Interval | How often to refresh data (seconds) | 600 (10 minutes) |
| Low Price Threshold | Price below which to trigger the low price alert | £1.40 |

## Sensors

The integration creates the following sensors:

| Sensor | Description | Example State |
|--------|-------------|---------------|
| `sensor.fuelfinder_cheapest` | The cheapest station and its price | `Tesco £1.42` |
| `sensor.fuelfinder_stations_in_range` | Number of stations found | `12` |
| `sensor.fuelfinder_nearby_stations` | Summary of nearby stations | `12 stations, best £1.42` |
| `sensor.fuelfinder_average_fuel_price` | Average price across all stations | `1.45` |
| `sensor.fuelfinder_distance_to_cheapest` | Distance to the cheapest station | `2.3 km` |

### Sensor Attributes

All sensors include rich attributes for scripting. The **Stations in Range** sensor includes:

- `all_stations` — full list of all stations with brand, price, distance, coordinates
- `station_1` through `station_10` — top 10 stations as individual attributes
- `average_price`, `best_price`, `home_latitude`, `home_longitude`

The **Nearby Stations** sensor includes:

- `stations_by_brand` — stations grouped by brand name
- `cheapest_by_brand` — the cheapest station for each brand

## Binary Sensors

| Sensor | Description |
|--------|-------------|
| `binary_sensor.fuelfinder_stations_available` | On when any stations are in range |
| `binary_sensor.fuelfinder_low_price_available` | On when fuel below your threshold is available |
| `binary_sensor.fuelfinder_best_price_nearby` | On when a station flagged as best price is nearby |

## Example Automations

### Notify when cheap fuel is available

```yaml
automation:
  - alias: "Cheap fuel alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.fuelfinder_low_price_available
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Cheap fuel nearby!"
          message: >
            Fuel from {{ state_attr('sensor.fuelfinder_cheapest', 'brand') }}
            at £{{ state_attr('sensor.fuelfinder_cheapest', 'lowest_price') }}
            ({{ state_attr('sensor.fuelfinder_cheapest', 'distance_display') }} away)
```

### Daily fuel price report

```yaml
automation:
  - alias: "Daily fuel report"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Morning fuel update"
          message: >
            Cheapest: {{ states('sensor.fuelfinder_cheapest') }}
            Average: £{{ states('sensor.fuelfinder_average_fuel_price') }}
            Stations: {{ states('sensor.fuelfinder_stations_in_range') }}
```

### Navigate to cheapest station

```yaml
automation:
  - alias: "Navigate to cheap fuel"
    trigger:
      - platform: state
        entity_id: binary_sensor.fuelfinder_low_price_available
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          message: "click"
          data:
            action: "URI"
            uri: >
              https://www.google.com/maps/dir/?api=1&destination=
              {{ state_attr('sensor.fuelfinder_cheapest', 'latitude') }},
              {{ state_attr('sensor.fuelfinder_cheapest', 'longitude') }}
```

## Template Examples

### Show cheapest station per brand in a card

```yaml
type: markdown
content: >
  {% set by_brand = state_attr('sensor.fuelfinder_nearby_stations', 'cheapest_by_brand') %}
  {% for brand, station in by_brand.items() %}
  **{{ brand }}**: £{{ station.lowest_price }} ({{ station.distance_display }})
  {% endfor %}
```

### Check if a specific brand has cheap fuel

```yaml
{{ state_attr('sensor.fuelfinder_nearby_stations', 'cheapest_by_brand').Tesco.lowest_price < 1.40 }}
```

## Requirements

- Home Assistant 2024.1.0 or newer
- Internet access to reach fuelaround.me
- Home location configured in Home Assistant

## Notes

- fuelaround.me primarily covers **UK fuel stations**. If your Home Assistant is located outside the UK, you may see limited or no results.
- The API is reverse-engineered from the fuelaround.me website and may change. The integration handles API errors gracefully and will log warnings if the format changes.
- Cloudflare protection on the site may occasionally block requests. The integration will retry automatically.

## License

MIT
