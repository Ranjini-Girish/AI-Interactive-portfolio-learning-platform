import { readFileSync } from "fs";

export function loadPipeline(path) {
  const raw = JSON.parse(readFileSync(path, "utf-8"));
  const nodes = new Map();
  for (const n of raw.nodes) {
    nodes.set(n.node_id, { ...n });
  }
  return {
    pipelineId: raw.pipeline_id,
    nodes,
    routingRules: raw.routing_rules,
    slidingWindowMs: raw.sliding_window_ms,
    latencyPerUnitWeight: raw.latency_per_unit_weight_ms,
  };
}

export function getNodeLatency(pipeline, nodeId) {
  const node = pipeline.nodes.get(nodeId);
  return Math.round(node.weight) * pipeline.latencyPerUnitWeight;
}

export function findAllPaths(pipeline) {
  const source = [...pipeline.nodes.values()].find(n => n.type === "source");
  const paths = [];

  function dfs(nodeId, currentPath) {
    currentPath.push(nodeId);
    const node = pipeline.nodes.get(nodeId);
    if (node.outputs.length === 0) {
      paths.push([...currentPath]);
    } else {
      for (const out of node.outputs) {
        dfs(out, currentPath);
      }
    }
    currentPath.pop();
  }

  dfs(source.node_id, []);
  return paths;
}
