function roundMoney(value) {
  return Math.round(value * 100) / 100;
}

function formatReport(report) {
  if (report.summary) {
    report.summary.total_sale_revenue = roundMoney(report.summary.total_sale_revenue);
    report.summary.total_purchase_cost = roundMoney(report.summary.total_purchase_cost);
  }
  return report;
}

module.exports = { roundMoney, formatReport };
