export function computeCategoryStats(processed, pipeline) {
  const cats = {};

  for (const evt of processed) {
    const cat = evt.category;
    if (!cats[cat]) cats[cat] = [];

    const latencies = evt.sinkResults.map(sr => sr.endToEndLatency);
    cats[cat].push({ priority: evt.priority, latencies });
  }

  const result = {};
  for (const cat of Object.keys(cats).sort()) {
    const entries = cats[cat];
    const count = entries.length;
    const avgPriority = round4(
      entries.reduce((s, e) => s + e.priority, 0) / count
    );

    let wSum = 0;
    let accum = 0;
    for (const e of entries) {
      for (const lat of e.latencies) {
        wSum += e.priority;
        accum += e.priority * lat;
      }
    }
    const weightedAvgLatency = round4(accum / wSum);

    result[cat] = {
      count,
      avgPriority,
      weightedAvgLatencyMs: weightedAvgLatency,
    };
  }

  return result;
}

function round4(x) {
  return Math.round(x * 10000) / 10000;
}
