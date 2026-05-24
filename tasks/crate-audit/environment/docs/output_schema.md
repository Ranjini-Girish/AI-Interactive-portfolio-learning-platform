# Output Schema

The audit report must be written to `/app/output/audit_report.json` with 2-space indentation and a trailing newline.

## Structure

    {
      "schema_version": 1,
      "resolution": {
        "total_packages": <integer>,
        "resolved": [<resolved_package>, ...]
      },
      "build_order": [<string>, ...],
      "audit": {
        "vulnerability_report": {
          "max_score": <float>,
          "critical_packages": [<vulnerability_entry>, ...],
          "total_vulnerable": <integer>
        },
        "license_report": {
          "conflicts": [<conflict_entry>, ...],
          "total_conflicts": <integer>
        },
        "statistics": {
          "total_packages": <integer>,
          "max_depth": <integer>,
          "avg_depth": <float>,
          "total_edges": <integer>,
          "max_fan_out": <integer>,
          "max_fan_in": <integer>
        }
      }
    }

## resolved_package

    {
      "name": <string>,
      "version": <string>,
      "license": <string>,
      "license_category": <string>,
      "depth": <integer>,
      "direct_dependencies": [<string "name@version">, ...],
      "dependents": [<string "name@version">, ...]
    }

The `license` field is the SPDX identifier from the registry. The `license_category` field is the category from the config's `license_categories` mapping ("permissive", "weak_copyleft", or "strong_copyleft"). If a license does not appear in any category, use "unknown".

The resolved array is sorted by depth ascending, then by package name ascending. Within each entry, direct_dependencies and dependents are sorted alphabetically.

## build_order

Array of strings in the form "name@version", representing the topological build order.

## vulnerability_entry

    {
      "name": <string>,
      "version": <string>,
      "base_score": <float>,
      "effective_score": <float>
    }

The critical_packages array is sorted by effective_score descending, then by name ascending. Scores are rounded to output_precision decimal places.

## conflict_entry

    {
      "package": <string "name@version">,
      "package_license": <string>,
      "dependency": <string "name@version">,
      "dependency_license": <string>
    }

The conflicts array is sorted by package name ascending.

## integrity_hash

The audit section must include an `integrity_hash` string that verifies the correctness of the resolution. Compute it as follows:

1. Collect all resolved packages sorted alphabetically by name.
2. For each package, format as `name:version:depth:license` (e.g. `logger:1.2.0:5:MIT`).
3. Join all entries with newline characters (`\n`).
4. Append a semicolon followed by the build order entries joined by semicolons (e.g. `\n` from step 3, then `;pkg1@ver1;pkg2@ver2;...`).
5. Compute the SHA-256 hex digest of the resulting UTF-8 string.

The structure becomes:

    "audit": {
      "vulnerability_report": { ... },
      "license_report": { ... },
      "statistics": { ... },
      "integrity_hash": <string>
    }

## Float Formatting

All float values in the output must be rounded to the number of decimal places specified by `output_precision` in the configuration file. Trailing zeros after the decimal point may be omitted — for example, with `output_precision: 4`, a value of `7.5` is acceptable (equivalent to `7.5000`). The value must always include at least one digit after the decimal point when it is not an integer (e.g. `7.5` not `7.50000`, but `0.0` for zero).
