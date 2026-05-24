function cloneConfig(config) {
  return { ...config };
}

function getWarehouseConfig(config, warehouseMeta) {
  const whConfig = cloneConfig(config);

  if (warehouseMeta.priority === 'high') {
    whConfig.thresholds.lowStockMultiplier = 2.0;
  }

  return whConfig;
}

function buildProductRanking(matchedTransactions) {
  const salesByProduct = {};

  for (const txn of matchedTransactions) {
    if (txn.type === 'sale') {
      const pid = txn.product.id;
      const name = txn.product.name;
      if (!salesByProduct[pid]) {
        salesByProduct[pid] = { product_id: pid, name: name, total_sold: 0 };
      }
      salesByProduct[pid].total_sold += txn.quantity;
    }
  }

  return Object.values(salesByProduct);
}

module.exports = { cloneConfig, getWarehouseConfig, buildProductRanking };
