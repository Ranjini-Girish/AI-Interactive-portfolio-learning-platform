import { getNodeLatency } from "./pipeline.js";

export function computeNodeStats(processed, pipeline) {
  const stats = {};

  for (const [nodeId] of pipeline.nodes) {
    stats[nodeId] = { eventsProcessed: 0, totalLatencyContribution: 0 };
  }

  for (const evt of processed) {
    for (const sr of evt.sinkResults) {
      for (const nl of sr.nodeLatencies) {
        stats[nl.nodeId].eventsProcessed += 1;
      }
    }
  }

  for (const [nodeId, s] of Object.entries(stats)) {
    s.totalLatencyContribution = s.eventsProcessed *
      getNodeLatency(pipeline, nodeId);
  }

  return stats;
}
