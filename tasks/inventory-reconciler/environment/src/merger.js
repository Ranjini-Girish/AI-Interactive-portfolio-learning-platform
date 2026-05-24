function normalizeId(id) {
  return id.replace("-", "").toUpperCase();
}

function buildProductIndex(products) {
  const index = {};
  for (const product of products) {
    const normalizedId = normalizeId(product.id);
    index[normalizedId] = product;
  }
  return index;
}

function mergeTransactions(products, transactions) {
  const productIndex = buildProductIndex(products);
  const matched = [];
  const unmatched = [];

  for (const txn of transactions) {
    const normalizedTxnId = txn.product_id.toUpperCase();
    const product = productIndex[normalizedTxnId];

    if (product) {
      matched.push({ ...txn, product });
    } else {
      unmatched.push(txn);
    }
  }

  return { matched, unmatched };
}

function mergeInventory(products, inventory) {
  const productIndex = buildProductIndex(products);
  const warehouseValues = {};

  for (const [warehouse, stock] of Object.entries(inventory)) {
    let totalValue = 0;
    for (const [productId, quantity] of Object.entries(stock)) {
      const normId = normalizeId(productId);
      const product = productIndex[normId];
      if (product) {
        totalValue += quantity * product.unit_price;
      }
    }
    warehouseValues[warehouse] = Math.round(totalValue * 100) / 100;
  }

  return warehouseValues;
}

module.exports = { normalizeId, buildProductIndex, mergeTransactions, mergeInventory };
