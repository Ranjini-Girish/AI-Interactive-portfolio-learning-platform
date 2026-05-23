# Edge Cases

## Azimuth Gap

Computed from the final event location to the unique set of stations that contributed
at least one **used** pick. Convert each station's bearing to degrees in `[0, 360)` using
`atan2(station.x - event.x, station.y - event.y)` (note: x is the east component, y is
the north component, so this gives the geographic azimuth measured clockwise from north).
Sort the angles, compute adjacent gaps including the wraparound gap
`(first_angle + 360 - last_angle)`, and take the maximum.
With fewer than two unique stations, the gap is `360.0`.

## Nearest Station

`nearest_station_km` is the minimum **horizontal** distance (2D, ignoring elevation and
depth) from the final event x/y location to any **enabled** station, not only those used.

## Depth Boundaries

If the final event depth is exactly `min_depth_km` or exactly `max_depth_km`, emit
a `depth_at_boundary` finding.

## Shallow Depth

If the final event depth is strictly less than `policy.shallow_depth_km`, emit a
`shallow_depth` finding.

## Station Distance Warning

If `nearest_station_km > policy.near_station_threshold_km`, the event is poorly
constrained; emit a `station_distance_warning` finding.
