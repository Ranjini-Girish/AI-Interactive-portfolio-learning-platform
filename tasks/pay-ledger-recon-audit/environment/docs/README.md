# Payments Ledger Reconciliation Auditor

A Python CLI that connects to a live SQLite payments ledger and produces a
deterministic JSON reconciliation report.

## Layout

- `audit/` — the CLI package (entry point: `python -m audit`)
- `data/` — policy, tenants, merchant rules, expected chain roots, and the
  SQL migrations used to seed `state.db`
- `scripts/init_db.sh` — rebuilds the live SQLite database from migrations
- `docs/` — schema and rule references

## Live database

The image is built with the seeded ledger materialized at:

```
/var/lib/audit/state.db
```

It is rebuilt at image build time from the SQL files under
`/app/data/migrations/`. The auditor opens this database read-only.

## Run

```
python -m audit \
    --db /var/lib/audit/state.db \
    --policy /app/data/policy.json \
    --out /app/out/reconciliation.json
```

The output JSON contract is defined by the task's `instruction.md` (the
authoritative source of truth for every field's semantics, sort order, and
edge case).

## Rebuilding the database

If you ever need a fresh state (e.g., after experimenting with
`UPDATE`/`INSERT` statements while exploring), simply re-run:

```
/app/scripts/init_db.sh
```
