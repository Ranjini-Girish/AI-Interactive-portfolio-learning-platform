# CLI Contract

The compiled binary lives at `/app/build/bfreplay` and accepts exactly
two positional arguments:

```
/app/build/bfreplay <data_dir> <out_dir>
```

## `data_dir` (argv[1])

The directory the binary reads three files from:
`<data_dir>/keys.json`, `<data_dir>/events.json`,
`<data_dir>/policy.json`. The binary must read from this argv-supplied
path; it must not fall back to a hardcoded `/app/data` when given a
different `<data_dir>`.

## `out_dir` (argv[2])

The directory the binary writes the five canonical JSON outputs to.
The binary must create the directory if it does not exist. It must
write to this argv-supplied path; it must not fall back to a hardcoded
`/app/output` when given a different `<out_dir>`.

## Exit status

The binary must exit non-zero in any of the following cases:

- The argument count is not exactly two (so `argc != 3` in C terms;
  zero, one, three, or more positional args all reject).
- Any of the three input files is missing.
- Any of the three input files fails to parse as UTF-8 JSON.
- The parsed JSON does not match the schema (e.g. an unknown `op`,
  a `key_idx` outside the closed key universe, or a `policy` field
  that is not in its allowed enum).
- The `hash_family` is not the literal string `"fnv1a_double_hashing"`.

Otherwise the binary must exit with status 0 after writing all five
output files. Stderr text is allowed for diagnostics but is not
inspected by the verifier.

## Build expectation

The verifier rebuilds the binary from the agent's `/app/src/*.cpp` and
`/app/include/*.h*` with a fresh
`g++ -std=c++17 -O2 -Wall -Wextra -I/app/include` invocation, runs the
rebuilt binary against the same `/app/data` (and against scratch
`<data_dir>` and `<out_dir>` paths), and compares its outputs to the
reference simulator byte-for-byte. A submission that ships a prebuilt
binary alongside dummy or empty `/app/src` sources cannot pass.
