The nightly reconciliation against `state.db` started flagging false positives last week. Fix the bugs in the audit CLI so it produces a correct report.

Run it via: `python -m audit --db /var/lib/audit/state.db --policy /app/data/policy.json --out /app/out/reconciliation.json`

The codebase under `/app/audit/` has several bugs introduced during a late-night deploy. The expected output schema and business rules are documented in `/app/docs/`. Cross-reference those docs with the existing code to find and fix the discrepancies. Don't modify files under `/app/data/` or the database itself.

The report must be valid JSON with UTF-8 encoding, two-space indentation, keys sorted alphabetically at every nesting level, and a trailing newline. Monetary values are integers (minor units). The verifier will run additional fixtures beyond the seeded data.
