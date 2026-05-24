import { sortEvents } from "./events.js";
import { findAllPaths, getNodeLatency } from "./pipeline.js";
import { resolveRoute } from "./routing.js";

export function processEvents(pipeline, events) {
  const sorted = sortEvents(events);
  const allPaths = findAllPaths(pipeline);
  const results = [];

  for (const evt of sorted) {
    const eventResults = [];

    for (const path of allPaths) {
      if (!isPathApplicable(pipeline, evt, path)) continue;

      let cumulative = 0;
      const nodeLatencies = [];
      for (const nodeId of path) {
        const lat = getNodeLatency(pipeline, nodeId);
        cumulative += lat;
        nodeLatencies.push({ nodeId, latency: lat });
      }

      const sinkId = path[path.length - 1];
      eventResults.push({
        path: [...path],
        sinkId,
        endToEndLatency: cumulative,
        arrivalTimestamp: evt.timestamp + cumulative,
        nodeLatencies,
      });
    }

    eventResults.sort((a, b) => a.sinkId.localeCompare(b.sinkId));

    results.push({
      eventId: evt.event_id,
      timestamp: evt.timestamp,
      priority: evt.payload.priority,
      category: evt.payload.category,
      payload: evt.payload,
      sinkResults: eventResults,
    });
  }

  return results;
}

function isPathApplicable(pipeline, event, path) {
  for (let i = 0; i < path.length; i++) {
    const nodeId = path[i];
    if (nodeId in pipeline.routingRules) {
      const dest = resolveRoute(pipeline.routingRules[nodeId], event.payload);
      if (i + 1 < path.length && path[i + 1] !== dest) {
        return false;
      }
    }
  }
  return true;
}
