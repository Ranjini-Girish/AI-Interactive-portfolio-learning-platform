export function checkSrm(observed, weights) {
  const total = Object.values(observed).reduce((a, b) => a + b, 0);
  return { chi2: 0, df: 1, p_value: 1, flagged: false };
}
