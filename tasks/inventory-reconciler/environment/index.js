const config = require('./src/config');
const { loadAllData } = require('./src/loader');
const { validateProductIds } = require('./src/validator');
const { mergeTransactions, mergeInventory } = require('./src/merger');
const { computeCategoryTotals, computeMedian, computeSaleRevenue, computePurchaseCost } = require('./src/calculator');
const { detectAnomalies } = require('./src/detector');
const { computeSupplierStats } = require('./src/aggregator');
const { formatReport } = require('./src/formatter');
const { getWarehouseConfig, buildProductRanking } = require('./src/utils');
const { writeReport } = require('./src/reporter');

function main() {
  const data = loadAllData(config.dataDir);

  // Stage 1: Validate
  const validation = validateProductIds(data.products);

  // Stage 2: Apply per-warehouse config (may modify shared config)
  for (const [whName, whMeta] of Object.entries(data.warehouses)) {
    getWarehouseConfig(config, whMeta);
  }

  // Stage 3: Merge
  const { matched, unmatched } = mergeTransactions(data.products, data.transactions);
  const warehouseValues = mergeInventory(data.products, data.inventory);

  // Stage 4: Calculate
  const categoryTotals = computeCategoryTotals(matched);
  const medianAmount = computeMedian(data.transactions);
  const totalSaleRevenue = computeSaleRevenue(matched);
  const totalPurchaseCost = computePurchaseCost(matched);

  // Stage 5: Detect
  const anomalies = detectAnomalies(data.products, data.inventory, data.suppliers, data.categories, config);

  // Stage 6: Aggregate
  const supplierStats = computeSupplierStats(data.suppliers);
  const productRanking = buildProductRanking(matched);

  // Stage 7: Format and write
  const report = formatReport({
    summary: {
      total_products: data.products.length,
      total_transactions: data.transactions.length,
      matched_products: matched.length,
      unmatched_products: unmatched.length,
      total_sale_revenue: totalSaleRevenue,
      total_purchase_cost: totalPurchaseCost,
      median_transaction_amount: medianAmount,
    },
    warehouse_values: warehouseValues,
    category_totals: categoryTotals,
    supplier_stats: supplierStats,
    anomalies: anomalies,
    validation: {
      total_checked: data.products.length,
      valid_count: validation.valid.length,
      invalid_count: validation.invalid.length,
      invalid_ids: validation.invalid,
    },
    product_ranking: productRanking,
  });

  const outPath = writeReport(report, config.outputDir, config.outputFile);
  console.log(`Report written to ${outPath}`);
}

main();
