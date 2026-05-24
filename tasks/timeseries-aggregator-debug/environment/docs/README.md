# Reference Notes

The sensor data aggregation tool processes CSV time-series data from industrial
sensors. Each sensor file follows a standard five-column CSV format. The
pipeline configuration is read from a single JSON file.

Sensor naming convention:
- TEMP-xx  : temperature sensors (celsius)
- HUMID-xx : humidity sensors (percent)
- PRESS-xx : pressure sensors (hpa)

Quality levels observed in data: good, acceptable, degraded.
