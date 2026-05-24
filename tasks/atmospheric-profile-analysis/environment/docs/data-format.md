# Data Format Reference

## Sounding Files

Each JSON file in `data/soundings/` represents a single atmospheric sounding with the following structure:

- `station_id`: string identifier matching an entry in stations.json
- `launch_time`: ISO 8601 timestamp of the radiosonde launch
- `levels`: array of atmospheric measurement levels, each containing:
  - `pressure`: atmospheric pressure in hectopascals (hPa)
  - `temperature`: air temperature in degrees Celsius
  - `dewpoint`: dewpoint temperature in degrees Celsius
  - `wind_direction`: wind direction in meteorological degrees (0=N, 90=E, 180=S, 270=W)
  - `wind_speed`: wind speed in meters per second
  - `height`: geopotential height above mean sea level in meters

Levels are ordered from lowest altitude (highest pressure) to highest altitude (lowest pressure).

## Station Metadata

The `stations.json` file contains an array of station objects with geographic coordinates (latitude, longitude), elevation above mean sea level, and a descriptive name.

## Configuration

The `config.json` file specifies physical constants, analysis method selections, and output formatting parameters.
