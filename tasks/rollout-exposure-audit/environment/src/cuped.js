export function cupedMean(rows, cov) {
  if (!rows.length) return 0;
  const ys = rows.map((r) => r.value ?? r);
  return ys.reduce((a, b) => a + b, 0) / ys.length;
}
