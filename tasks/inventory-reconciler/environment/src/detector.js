function detectAnomalies(products, inventory, suppliers, categories, config) {
  const anomalies = [];
  const allStock = {};

  for (const [wh, stock] of Object.entries(inventory)) {
    for (const [pid, qty] of Object.entries(stock)) {
      allStock[pid] = (allStock[pid] || 0) + qty;
    }
  }

  for (const product of products) {
    const qty = allStock[product.id] || 0;
    const catInfo = categories[product.category];

    const threshold = (catInfo ? catInfo.min_stock : 0) * (config.thresholds.lowStockMultiplier || 1);
    if (catInfo && qty < threshold) {
      anomalies.push({
        type: 'low_stock',
        product_id: product.id,
        details: `Stock ${qty} below minimum ${threshold} for ${product.category}`,
      });
    }

    const supplierEntry = suppliers[product.id];
    if (typeof supplierEntry === 'object') {
      // supplier info available — nothing to flag
    } else {
      anomalies.push({
        type: 'no_supplier',
        product_id: product.id,
        details: `No supplier record for ${product.name}`,
      });
    }
  }

  anomalies.sort((a, b) => a.product_id.localeCompare(b.product_id));
  return anomalies;
}

module.exports = { detectAnomalies };
