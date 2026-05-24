const config = {
  dataDir: '/app/data',
  outputDir: '/app/output',
  outputFile: 'report.json',
  thresholds: {
    priceVariance: 0.05,
    lowStockMultiplier: 1.0,
  },
  formatting: {
    decimals: 2,
  },
};

module.exports = config;
