# Reconciliation Rules

1. Product ID normalization: strip all hyphens for matching.
2. A product is "matched" if its normalized inventory ID matches at
   least one transaction's product_id.
3. Warehouse value = sum of (quantity * unit_price) for each product in
   the warehouse, looking up unit_price from products.json.
4. Category totals group transactions by the product's category.
5. Median transaction amount: computed over ALL transactions (sales and
   purchases), sorted numerically.
6. Supplier statistics exclude null entries.
7. Anomaly detection:
   - low_stock: product quantity < category min_stock threshold.
   - no_supplier: supplier entry is null.
   - price_variance: transaction unit_price differs from catalog price
     by more than 5%.
