function computeSupplierStats(suppliers) {
  let count = 0;
  let totalRating = 0;
  let totalLeadDays = 0;
  let nullCount = 0;

  for (const [pid, info] of Object.entries(suppliers)) {
    if (info === null || info === undefined) {
      nullCount++;
      continue;
    }
    count++;
    totalRating += info.rating;
    totalLeadDays += info.lead_days;
  }

  return {
    total_suppliers: count,
    avg_rating: count > 0 ? Math.round(totalRating / count * 100) / 100 : 0,
    avg_lead_days: count > 0 ? Math.round(totalLeadDays / count * 100) / 100 : 0,
    products_without_supplier: nullCount,
  };
}

module.exports = { computeSupplierStats };
