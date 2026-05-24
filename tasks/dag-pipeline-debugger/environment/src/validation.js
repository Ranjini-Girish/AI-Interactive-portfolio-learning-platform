export function validatePipeline(pipeline) {
  const nodeIds = new Set(pipeline.nodes.keys());
  const errors = [];

  for (const [nodeId, node] of pipeline.nodes) {
    for (const out of node.outputs) {
      if (!nodeIds.has(out)) {
        errors.push(`Node ${nodeId} references unknown output ${out}`);
      }
    }
  }

  const sources = [...pipeline.nodes.values()].filter(n => n.type === "source");
  if (sources.length !== 1) {
    errors.push(`Expected exactly 1 source node, found ${sources.length}`);
  }

  const sinks = [...pipeline.nodes.values()].filter(n => n.type === "sink");
  if (sinks.length === 0) {
    errors.push("No sink nodes found");
  }

  for (const sink of sinks) {
    if (sink.outputs.length > 0) {
      errors.push(`Sink node ${sink.node_id} has outputs`);
    }
  }

  return errors;
}

export function validateEvents(events) {
  const errors = [];
  const ids = new Set();

  for (const evt of events) {
    if (ids.has(evt.event_id)) {
      errors.push(`Duplicate event_id: ${evt.event_id}`);
    }
    ids.add(evt.event_id);

    if (typeof evt.timestamp !== "number" || evt.timestamp < 0) {
      errors.push(`Invalid timestamp for ${evt.event_id}`);
    }

    if (!evt.payload || typeof evt.payload !== "object") {
      errors.push(`Missing or invalid payload for ${evt.event_id}`);
    }
  }

  return errors;
}
