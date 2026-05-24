# Output Format

Produce `/app/output/execution_report.json` with two-space indent and a trailing newline.

## Top-Level Structure

- `schema_version` — integer, must be 1
- `machine_config` — echo of the fields from `config.json`
- `program_results` — array sorted by `program` name ascending
- `summary` — aggregate statistics

## Program Result Entry

Each entry in `program_results`:

- `program` — the program name (from the JSON `name` field)
- `status` — `"halted"` or `"timeout"`
- `cycles` — integer count of executed instructions
- `registers` — array of 8 integers [R0, R1, ..., R7]
- `flags` — object with keys `zero`, `negative`, `overflow`, `error` (booleans)
- `stack_pointer` — integer
- `memory_writes` — total count of successful 32-bit writes to memory (includes PUSH, CALL, and STORE)
- `error_log` — array of error entries sorted by `cycle` ascending

## Error Log Entry

Each entry in `error_log`:

- `cycle` — the cycle number when the error occurred
- `pc` — the program counter at the time of the error
- `error` — one of `"division_by_zero"`, `"stack_underflow"`, `"stack_overflow"`, `"memory_out_of_bounds"`

## Summary

- `total_programs` — total number of programs executed
- `halted` — count of programs that reached HALT
- `timeout` — count of programs that exceeded max_cycles
- `total_cycles` — sum of cycles across all programs
- `total_errors` — sum of error log entries across all programs
