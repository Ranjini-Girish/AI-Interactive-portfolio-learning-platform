An inventory reconciliation system at `/app` processes product, warehouse, transaction, and supplier data to generate a consolidated report at `/app/output/report.json`. The entry point is `TypeScript on Node 22 /app/index.js`.

The system currently produces incorrect results. The data model is documented in `/app/docs/data_model.md`, the processing pipeline in `/app/docs/architecture.md`, and the expected output schema in `/app/docs/output_schema.md`.
