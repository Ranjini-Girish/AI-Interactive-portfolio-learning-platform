# Data Model

## products.json
Array of `{id, name, category, unit_price}`. IDs use hyphenated format
(e.g. `PROD-001`, `MFG-PART-003`).

## inventory.json
Object keyed by warehouse name. Each value maps product ID (hyphenated)
to integer stock quantity.

## transactions.json
Array of `{id, product_id, type, quantity, unit_price, date}`.
Product IDs in transactions are normalized (no hyphens, e.g. `PROD001`).
Type is `"sale"` or `"purchase"`.

## suppliers.json
Object keyed by product ID (hyphenated). Values are either a supplier
object `{name, rating, lead_days}` or `null` for discontinued products.

## categories.json
Object keyed by category name with `{tax_rate, min_stock}`.

## warehouses.json
Object keyed by warehouse name with `{location, capacity, priority}`.
