# Linker Symbol Resolver

A simplified linker that reads JSON-format object files, resolves symbols, merges sections, and applies relocations.

## Building

```bash
make -C /app all
```

## Running

```bash
/app/build/linker [config_path] [output_path]
```

Defaults: reads `/app/data/link_config.json`, writes `/app/output/link_report.json`.

## Project Structure

- `include/json.h` — Minimal JSON parser/serializer
- `include/linker/` — Header files defining types and interfaces
- `src/` — Source files (stubs to be implemented)
- `data/` — Input data (object files, config)
- `data/docs/` — Architecture documentation
