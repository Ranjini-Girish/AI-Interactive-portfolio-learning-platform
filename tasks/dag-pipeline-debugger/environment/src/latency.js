export function computeLatencySummary(processed) {
  const allLatencies = [];

  for (const evt of processed) {
    for (const sr of evt.sinkResults) {
      allLatencies.push(sr.endToEndLatency);
    }
  }

  const sum = allLatencies.reduce((s, v) => s + v, 0);
  const avg = Math.ceil(sum * 10000 / allLatencies.length) / 10000;

  return {
    avgEndToEndLatencyMs: avg,
    maxEndToEndLatencyMs: Math.max(...allLatencies),
    minEndToEndLatencyMs: Math.min(...allLatencies),
  };
}
