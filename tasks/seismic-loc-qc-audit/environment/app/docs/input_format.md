# Input Files

The tool reads fixture data from the directory passed via `--data` (default `/app/data`).

`network/stations.csv` has header `station_id,x_km,y_km,elevation_km,bias_s,enabled`.
Coordinates are local Cartesian kilometers. `elevation_km` is positive above the datum;
event depth is positive below the datum. A station is usable only when `enabled` is
exactly `true`.

`velocity/velocity_layers.csv` has header `phase,top_depth_km,bottom_depth_km,velocity_km_s`.
Phase is `P` or `S`. For a candidate event depth, look up the row whose phase matches the
pick's phase and whose interval contains the depth: the lower bound `top_depth_km` is
inclusive; the upper bound `bottom_depth_km` is exclusive **except** for the deepest layer
of that phase, whose upper bound is inclusive. Never substitute a P velocity for an S pick.

`catalog/events.csv` has header
`event_id,prior_x_km,prior_y_km,prior_depth_km,prior_origin_time_s,status`.
Events whose status is exactly `exclude` or `void` are output with status `excluded`.
Events listed in `exclusions.json` `excluded_events` are also excluded.
All other statuses — including the empty string — are processable.

`picks/picks.csv` has header
`pick_id,event_id,station_id,phase,arrival_time_s,weight,status,amplitude`.
A pick is eligible only when:
- Its event is processable.
- Its station exists in `network/stations.csv` **and** is enabled.
- Its station is not listed in `exclusions.json` `excluded_stations`.
- Its phase has a velocity layer for the tested depth.
- Its `weight` is strictly positive.
- Its status is exactly `use`.
Ineligible picks count as rejected picks in the event summary. There are also
per-event pick files `picks/picks_evt_x.csv` but these are informational only;
the canonical source is `picks/picks.csv`.

`policy.json` contains all numeric thresholds and severity mappings.
`magnitude_model.json` contains `reference_amplitude`, `reference_distance_km`, and
`log_base` for the local magnitude formula.
`exclusions.json` contains `excluded_stations` and `excluded_events` arrays.
