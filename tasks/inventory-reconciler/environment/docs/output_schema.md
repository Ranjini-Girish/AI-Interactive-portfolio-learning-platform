# Output Schema — `/app/output/report.json`

```json
{
  "summary": {
    "total_products": <int>,
    "total_transactions": <int>,
    "matched_products": <int>,
    "unmatched_products": <int>,
    "total_sale_revenue": <float>,
    "total_purchase_cost": <float>,
    "median_transaction_amount": <float>
  },
  "warehouse_values": {
    "<warehouse_name>": <float (inventory value = sum of qty * unit_price)>
  },
  "category_totals": {
    "<category>": {
      "sale_count": <int>,
      "sale_revenue": <float>,
      "purchase_count": <int>,
      "purchase_cost": <float>
    }
  },
  "supplier_stats": {
    "total_suppliers": <int>,
    "avg_rating": <float>,
    "avg_lead_days": <float>,
    "products_without_supplier": <int>
  },
  "anomalies": [
    {
      "type": "<low_stock|no_supplier|price_variance>",
      "product_id": "<id>",
      "details": "<description>"
    }
  ],
  "validation": {
    "total_checked": <int>,
    "valid_count": <int>,
    "invalid_count": <int>,
    "invalid_ids": [<string>]
  },
  "product_ranking": [
    {"product_id": "<id>", "name": "<name>", "total_sold": <int>}
  ]
}
```

- All monetary values rounded to 2 decimal places.
- `product_ranking` sorted alphabetically by product name.
- `anomalies` sorted by product_id.
- `warehouse_values` computed from inventory quantities * product unit prices.
- Only products with valid IDs contribute to matched/category counts.
- `supplier_stats.avg_rating` and `avg_lead_days` computed over non-null
  suppliers only.
