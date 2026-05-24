function computeCategoryTotals(matchedTransactions) {
  const totals = {};

  for (const txn of matchedTransactions) {
    const cat = txn.product.category;
    if (!totals[cat]) {
      totals[cat] = { sale_count: 0, sale_revenue: 0, purchase_count: 0, purchase_cost: 0 };
    }

    const amount = Math.round(txn.quantity * txn.unit_price * 100) / 100;

    if (txn.type === 'sale') {
      totals[cat].sale_count += 1;
      totals[cat].sale_revenue += amount;
    } else {
      totals[cat].purchase_count += 1;
      totals[cat].purchase_cost += amount;
    }
  }

  for (const cat of Object.keys(totals)) {
    totals[cat].sale_revenue = Math.round(totals[cat].sale_revenue * 100) / 100;
    totals[cat].purchase_cost = Math.round(totals[cat].purchase_cost * 100) / 100;
  }

  return totals;
}

function computeMedian(transactions) {
  const amounts = transactions.map(t => Math.round(t.quantity * t.unit_price * 100) / 100);
  amounts.sort();
  const mid = Math.floor(amounts.length / 2);
  if (amounts.length % 2 === 0) {
    return Math.round((amounts[mid - 1] + amounts[mid]) / 2 * 100) / 100;
  }
  return amounts[mid];
}

function computeSaleRevenue(matchedTransactions) {
  let total = 0;
  for (const txn of matchedTransactions) {
    if (txn.type === 'sale') {
      total += Math.round(txn.quantity * txn.unit_price * 100) / 100;
    }
  }
  return Math.round(total * 100) / 100;
}

function computePurchaseCost(matchedTransactions) {
  let total = 0;
  for (const txn of matchedTransactions) {
    if (txn.type === 'purchase') {
      total += Math.round(txn.quantity * txn.unit_price * 100) / 100;
    }
  }
  return Math.round(total * 100) / 100;
}

module.exports = { computeCategoryTotals, computeMedian, computeSaleRevenue, computePurchaseCost };
