# Output Format Specification

The output file `/app/output/solution.json` must be valid JSON with 2-space
indentation and a trailing newline.

## Top-Level Keys (in order)

1. "metadata"
2. "node_temperatures" 
3. "element_data"
4. "summary"

## metadata

```json
{
  "solver_type": "conjugate_gradient",
  "preconditioner": "jacobi",
  "mesh_nodes": 36,
  "mesh_elements": 50,
  "convergence": {
    "converged": true,
    "iterations": <int>,
    "final_residual": <float>
  }
}
```

## node_temperatures

Array of objects sorted by node_id:
```json
[
  {"node_id": 0, "x": 0.0, "y": 0.0, "temperature": 100.0},
  ...
]
```

## element_data

Array of objects sorted by element_id:
```json
[
  {
    "element_id": 0,
    "nodes": [0, 1, 6],
    "avg_temperature": <float>,
    "heat_flux_x": <float>,
    "heat_flux_y": <float>
  },
  ...
]
```

Heat flux components use the formula from fem_spec.md.

## summary

```json
{
  "min_temperature": <float>,
  "max_temperature": <float>,
  "mean_temperature": <float>,
  "total_heat_flux_x": <float>,
  "total_heat_flux_y": <float>
}
```

All floats rounded to 6 decimal places.
