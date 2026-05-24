# Transaction Reconciliation Pipeline

Reconciles financial transactions across ingestion, settlement, and ledger stages.

## Project Structure

- `data/` — Input CSV files and schema example
- `config/` — Exchange rates and threshold configuration
- `scripts/` — Pipeline scripts (stubs to be implemented)
- `lib/` — Shared awk libraries
- `docs/` — Business rules and error definitions

## Available Tools

The environment provides: `gawk`, `jq`, `bc`, and standard coreutils.
