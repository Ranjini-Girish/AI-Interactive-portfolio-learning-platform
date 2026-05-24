export function computeSinkStats(processed, pipeline) {
  const windowMs = pipeline.slidingWindowMs;
  const sinkArrivals = {};

  for (const evt of processed) {
    for (const sr of evt.sinkResults) {
      if (!sinkArrivals[sr.sinkId]) sinkArrivals[sr.sinkId] = [];
      sinkArrivals[sr.sinkId].push(sr.arrivalTimestamp);
    }
  }

  const result = {};
  for (const sinkId of Object.keys(sinkArrivals).sort()) {
    const arrivals = sinkArrivals[sinkId].sort((a, b) => a - b);
    let maxThroughput = 0;

    for (const arrTs of arrivals) {
      const windowStart = arrTs - windowMs;
      let count = 0;
      for (const a of arrivals) {
        if (a <= windowStart) continue;
        if (a <= arrTs) count++;
      }
      if (count > maxThroughput) maxThroughput = count;
    }

    result[sinkId] = {
      eventsReceived: arrivals.length,
      maxWindowThroughput: maxThroughput,
    };
  }

  return result;
}
