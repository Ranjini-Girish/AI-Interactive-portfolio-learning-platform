# Output Schema: geometry_audit.json

Write to `/app/output/geometry_audit.json`.

## Top-Level Structure

```json
{
  "schema_version": 1,
  "summary": { ... },
  "source_sha256": { ... },
  "scene_audits": [ ... ],
  "findings": [ ... ]
}
```

## `summary`

| Field                | Type   | Description                                    |
|----------------------|--------|------------------------------------------------|
| `total_scenes`       | int    | Number of scenes analysed                      |
| `total_polygons`     | int    | Total polygons across all scenes               |
| `total_findings`     | int    | Total findings across all scenes               |
| `findings_by_type`   | object | `{ finding_type: count }` sorted by key        |
| `findings_by_severity` | object | `{ severity: count }` for each of critical/high/medium/low/info (always present, 0 if none) |

## `source_sha256`

Object mapping relative paths (from `/app/`) of every file under
`config/`, `scenes/`, and `queries/` to their SHA-256 hex digest.
Sorted by key. Forward-slash path separators.

## `scene_audits`

Array sorted by `scene_id`. Each object contains whichever analyses
were requested by the corresponding query file.

### `polygon_properties` (when requested)

Array of objects, one per polygon:

| Field          | Type    | Description                          |
|----------------|---------|--------------------------------------|
| `polygon_id`   | string  | Identifier                           |
| `vertex_count` | int     | Number of vertices                   |
| `signed_area`  | float   | Signed area (positive=CCW)           |
| `area`         | float   | Absolute area                        |
| `perimeter`    | float   | Sum of edge lengths                  |
| `centroid`     | [x,y]   | Centroid coordinates                 |
| `orientation`  | string  | `"CCW"`, `"CW"`, or `"degenerate"`  |
| `is_convex`    | bool    | True if all cross products agree     |
| `is_simple`    | bool    | True if no self-intersection         |
| `bounding_box` | object  | `{min_x, min_y, max_x, max_y}`      |

### `convex_hull` (when requested)

| Field          | Type  | Description                           |
|----------------|-------|---------------------------------------|
| `vertices`     | array | Hull vertices in CCW order            |
| `vertex_count` | int   | Number of hull vertices               |
| `area`         | float | Area of the convex hull               |
| `perimeter`    | float | Perimeter of the convex hull          |

Hull includes all standalone points and all polygon vertices.

### `point_in_polygon` (when requested)

Array of test results:

```json
{"point_idx": 0, "point": [x, y], "polygon_id": "...", "result": "inside|outside|boundary"}
```

### `segment_intersections` (when requested)

Array sorted by `(segment_a, segment_b)`:

```json
{"segment_a": 0, "segment_b": 1, "point": [x, y]}
```

### `closest_pair` (when requested)

```json
{"point_a_idx": 0, "point_b_idx": 1, "distance": 2.5}
```

Tie-break: smallest `(point_a_idx, point_b_idx)`.

### `min_enclosing_circle` (when requested)

```json
{"center": [x, y], "radius": 5.0}
```

### `findings`

Per-scene findings sorted by `(severity_rank, finding_type, polygon_id)`.
Each finding object contains:

| Field          | Type        | Description                                     |
|----------------|-------------|-------------------------------------------------|
| `finding_type` | string      | Type identifier                                 |
| `severity`     | string      | Severity level from `policy.json`               |
| `scene_id`     | string      | Scene containing the finding                    |
| `polygon_id`   | string/null | Associated polygon; `null` for point findings   |
| `evidence`     | object      | Supporting data specific to the finding type     |

#### Evidence by finding type

| Finding type                | Evidence fields                                |
|-----------------------------|------------------------------------------------|
| `degenerate_polygon`        | `area` (float), `vertex_count` (int)           |
| `self_intersecting_polygon` | `polygon_id` (string)                          |
| `duplicate_points`          | `point` ([x, y] coordinate of the duplicate)   |

For `duplicate_points`, one finding is generated for each distinct
coordinate that appears more than once among the standalone points.

## Global `findings`

Aggregation of all per-scene findings, sorted by
`(severity_rank, finding_type, scene_id, polygon_id)`.

All floating-point values rounded to `output_decimals` decimal places
(from `policy.json`).
