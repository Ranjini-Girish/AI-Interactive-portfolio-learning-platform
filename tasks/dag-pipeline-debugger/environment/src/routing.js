export function resolveRoute(rule, payload) {
  const value = payload[rule.field];
  if (value >= rule.threshold) {
    return rule.above;
  }
  return rule.at_or_below;
}
