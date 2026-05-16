# Tabular gap bundle — normative specification

This document is the binding contract for every structural rule. The workspace prompt names paths, the binary, and the deliverable; all schema, missingness, masking, dedup, percentage, sort, and JSON layout rules live here. Whenever the prose admits two readings, the rule below is the one the verifier compares against.

## Inputs

All paths are rooted at `/app/tab_bundle/`.

- `catalog.json` lists the TSV inputs to process under the key `inputs`. Each element is an object with string fields `dataset_id` and `relative_path`. Iterate `inputs` in array order to assign global row indices and to sequence per-dataset processing.
- `policy.json` provides four arrays of strings: `extra_missing_tokens`, `rollup_skip_columns`, `dedup_keys`, and `global_keys`. Treat each as an unordered set for semantics; emit the first two sorted ascending in `meta` and use the others as keys for duplicate detection as defined below.
- Only files referenced by `relative_path` from `catalog.json` are read as TSV tables. Any other regular file under `/app/tab_bundle/` exists only as a distractor and must not be opened or otherwise influence the report.

## TSV grammar

When reading a table file, if the raw bytes end with a single POSIX line feed (`\n`) after the final line's content, discard that terminator before splitting into lines; it is not itself a data row.

Each table file begins with a header line whose tab-separated tokens are the column names from left to right. Each subsequent line is a data row whose tab-separated tokens are field values. A completely empty line after the header is still a data row whose every header column is the empty string. If a data line has fewer tab-separated tokens than the header, pad missing trailing fields with the empty string. Never trim leading or trailing whitespace inside a token; the only field boundary is the tab character.

## Per-table kept columns and the global union

For each table, walk header tokens left to right and drop any column whose name appears in `policy.rollup_skip_columns`. The remaining columns form the **per-table kept columns** for that dataset, in their original header order.

The **global kept columns** are the union of per-table kept columns across every cataloged dataset, sorted ascending by raw UTF-8 byte string using C-locale collation (lexicographic order of Unicode code points). The number of distinct names in this union is `summary.kept_column_count`.

Per-table schemas are heterogeneous: a column may appear as kept in one dataset and be absent in another. The mask construction, column rollups, and dataset rollups all operate against the global union, not a per-table column list.

## Missing value predicate

A field value `v` is **missing** when any of the following holds:

1. `v` is the empty string.
2. `v` consists only of ASCII space, tab, carriage return, or newline characters.
3. `v` is exactly the two-character string `NA` (case-sensitive, full-field match).
4. `v` is exactly equal, as a whole field, to one of the strings listed in `policy.extra_missing_tokens` (case-sensitive, full-field match).

Otherwise `v` is **present**.

A column that is **not in the per-table kept columns** of a given dataset has no value for any row in that dataset; treat such a column-row pair as missing for every purpose below (mask bit, column rollup count, dataset rollup count). This applies even when the column appears under `policy.rollup_skip_columns` in the same dataset's header — the dataset still contributes a missing entry for that column to the global rollup.

## Row indexing

Within each dataset, data rows are numbered starting at 1 in top-to-bottom file order. The first data line after the header is `row_index = 1`.

The **global row index** is a monotonically increasing counter over all data rows of all cataloged datasets, walked in catalog array order and within each table in row order. The first data row in the first cataloged table has `global_index = 1`. Every data row consumes exactly one global index, including rows that are skipped by either duplicate-detection system below.

## Presence mask

For every data row in every cataloged dataset, emit a string `mask` whose length equals the number of names in the global kept columns. Walk the global kept columns in their lexicographic order. For each name `c`:

- If `c` is in the per-table kept columns of this dataset, look up the value for `c` in this row and append `0` if missing, otherwise `1`.
- If `c` is not in the per-table kept columns of this dataset, append `0`.

Do not insert separators inside `mask`.

## Column rollups

For each name `c` in the global kept columns, aggregate across every data row of every cataloged dataset:

- `total_rows` is the sum of data rows across all cataloged tables (the same number for every column; it equals `summary.total_data_rows`).
- `missing_count` counts rows whose `c` bit in the mask is `0`.
- `present_count` is `total_rows - missing_count`.

Rates are formatted strings with exactly six digits after the decimal point and no leading zeros in the integer part except the single zero when the integer part is zero. Compute each rate by truncating the exact rational `count * 100 / total_rows` toward zero at the sixth decimal place when `total_rows > 0`. When `total_rows` is zero, both rates are `0.000000`. When `missing_count == total_rows`, force `missing_rate = "100.000000"` and `present_rate = "0.000000"`. When `present_count == total_rows`, force `missing_rate = "0.000000"` and `present_rate = "100.000000"`.

## Dataset rollups

For each cataloged dataset, compute:

- `dataset_id`: copied verbatim from `catalog.json`.
- `data_rows`: integer count of data rows in this dataset.
- `kept_columns_present`: per-table kept column names sorted ascending by raw UTF-8 byte string using C-locale collation.
- `cells_total`: `data_rows` multiplied by the number of names in the global kept columns.
- `missing_count`: sum across this dataset's rows of the number of `0` bits in the mask.
- `missing_rate_dataset`: formatted string with the same six-digit truncation rule as column rollups, where the rate is `missing_count * 100 / cells_total` when `cells_total > 0`. When `cells_total` is zero, the rate is `"0.000000"`. Apply the same `0.000000` / `100.000000` boundary clamps as the column rule.

## Per-dataset duplicate key events

For each cataloged dataset:

- If any name in `policy.dedup_keys` is not in the per-table kept columns of this dataset, the dataset is **dedup-disabled**. Emit no events for it and skip the rest of this section.
- Otherwise walk this dataset's rows in row-index order. For each row:
  - Build the **composite key** as a JSON array of string values, taking the values for the columns in `policy.dedup_keys` in the lexicographic order of those column names.
  - If any value in that composite key is missing per the missing-value predicate, skip this row entirely (no event recorded, no first-occurrence registered).
  - Otherwise look up the composite key in this dataset's first-occurrence map. If absent, register the row's index as the first occurrence and continue. If present, emit one event with fields `dataset_id`, `key_value` (the composite key array), `first_row_index` (the registered first occurrence), and `later_row_index` (this row's index).

The first-occurrence map is private to each dataset; it is not shared across datasets.

## Global key events

Walk every data row in global iteration order. For each row:

- Build the **global key** as a JSON array of string values, taking the values for the columns in `policy.global_keys` in the lexicographic order of those column names. A column that is not in the per-table kept columns of the current dataset contributes a missing value.
- If any value in the global key is missing per the missing-value predicate, skip this row (no event recorded, no first-occurrence registered) but the row still consumes its global index.
- Otherwise look up the global key in a single map shared across all datasets. If absent, register `(dataset_id, global_index)` as the first occurrence. If present, emit one event with fields `key_value`, `first_dataset_id`, `first_global_index`, `later_dataset_id`, and `later_global_index`. The first occurrence is never overwritten by subsequent matches.

A second match in the same dataset still produces a global key event; this stream is independent of the per-dataset duplicate stream.

## Output artifact

Write exactly one regular file `/app/audit/gap_report.json`. The bytes must be UTF-8 without a byte order mark. Use two-space indentation, sort object keys ascending at every object level by raw UTF-8 byte string, write all string values as ASCII-only text (the bundled fixtures contain only ASCII), and end the file with a single newline character after the final closing brace with no additional trailing bytes. Two correct runs must be byte-identical.

## Required top-level keys

The top-level JSON object must contain exactly these keys: `column_rollups`, `dataset_rollups`, `duplicate_key_events`, `global_key_events`, `meta`, `presence_rows`, `summary`.

### `meta`

Object fields:

- `catalog_sha256`: lowercase hexadecimal SHA-256 digest of the raw bytes of `/app/tab_bundle/catalog.json`.
- `extra_missing_tokens`: `policy.extra_missing_tokens` sorted ascending by raw UTF-8 byte string.
- `global_keys`: `policy.global_keys` sorted ascending by raw UTF-8 byte string.
- `dedup_keys`: `policy.dedup_keys` sorted ascending by raw UTF-8 byte string.
- `rollup_skip_columns`: `policy.rollup_skip_columns` sorted ascending by raw UTF-8 byte string.

### `summary`

Object fields, all integers:

- `catalog_inputs`: count of entries in `catalog.json` `inputs`.
- `kept_column_count`: number of distinct names in the global kept columns union.
- `total_data_rows`: sum of data rows across all cataloged tables.
- `duplicate_key_events`: total count of per-dataset duplicate events.
- `global_key_events`: total count of global key events.

### `column_rollups`

Each object has exactly the keys `column_name`, `missing_count`, `missing_rate`, `present_count`, `present_rate`, `total_rows`. All counts are JSON integers; both rates are JSON strings as specified. Sort the array by descending decimal value of `missing_rate`, then descending integer `missing_count`, then ascending `column_name` by raw UTF-8 byte string.

### `dataset_rollups`

Each object has exactly the keys `cells_total`, `data_rows`, `dataset_id`, `kept_columns_present`, `missing_count`, `missing_rate_dataset`. Sort the array by descending decimal value of `missing_rate_dataset`, then descending integer `data_rows`, then ascending `dataset_id` by raw UTF-8 byte string.

### `presence_rows`

Each object has exactly the keys `dataset_id` (string), `mask` (string), `row_index` (integer). Sort the array ascending by `dataset_id` (raw UTF-8 byte string), then ascending by integer `row_index`.

### `duplicate_key_events`

Each object has exactly the keys `dataset_id` (string), `first_row_index` (integer), `key_value` (array of strings), `later_row_index` (integer). Sort the array ascending by `dataset_id`, then ascending by `key_value` array (element-wise byte-string comparison), then ascending by `later_row_index`, then ascending by `first_row_index`.

### `global_key_events`

Each object has exactly the keys `first_dataset_id` (string), `first_global_index` (integer), `key_value` (array of strings), `later_dataset_id` (string), `later_global_index` (integer). Sort the array ascending by `key_value` array, then ascending by `later_global_index`, then ascending by `first_global_index`.

## Prohibited writes

Never modify, create, or delete anything under `/app/tab_bundle/`. Only create `/app/audit/` if needed and write `gap_report.json` there.
