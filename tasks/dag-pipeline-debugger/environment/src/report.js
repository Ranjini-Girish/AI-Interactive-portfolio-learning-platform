export function buildReport(
  pipeline, processed, nodeStats, sinkStats,
  categoryStats, latencySummary, integrityHash
) {
  const sortedNodeStats = {};
  for (const nodeId of Object.keys(nodeStats).sort()) {
    const ns = nodeStats[nodeId];
    sortedNodeStats[nodeId] = {
      events_processed: ns.eventsProcessed,
      total_latency_contribution_ms: ns.totalLatencyContribution,
    };
  }

  const sortedSinkStats = {};
  for (const sinkId of Object.keys(sinkStats).sort()) {
    const ss = sinkStats[sinkId];
    sortedSinkStats[sinkId] = {
      events_received: ss.eventsReceived,
      max_window_throughput: ss.maxWindowThroughput,
    };
  }

  const sortedCategoryStats = {};
  for (const cat of Object.keys(categoryStats).sort()) {
    const cs = categoryStats[cat];
    sortedCategoryStats[cat] = {
      count: cs.count,
      avg_priority: cs.avgPriority,
      weighted_avg_latency_ms: cs.weightedAvgLatencyMs,
    };
  }

  let sinkACount = 0;
  let sinkBCount = 0;
  let archiveCount = 0;
  for (const evt of processed) {
    for (const sr of evt.sinkResults) {
      if (sr.sinkId === "sink_a") sinkACount++;
      else if (sr.sinkId === "sink_b") sinkBCount++;
      else if (sr.sinkId === "archive") archiveCount++;
    }
  }

  return {
    pipeline_id: pipeline.pipelineId,
    total_events: processed.length,
    node_stats: sortedNodeStats,
    sink_stats: sortedSinkStats,
    category_stats: sortedCategoryStats,
    routing_summary: {
      sink_a_count: sinkACount,
      sink_b_count: sinkBCount,
      archive_count: archiveCount,
    },
    latency_summary: {
      avg_end_to_end_latency_ms: latencySummary.avgEndToEndLatencyMs,
      max_end_to_end_latency_ms: latencySummary.maxEndToEndLatencyMs,
      min_end_to_end_latency_ms: latencySummary.minEndToEndLatencyMs,
    },
    integrity_hash: integrityHash,
  };
}
