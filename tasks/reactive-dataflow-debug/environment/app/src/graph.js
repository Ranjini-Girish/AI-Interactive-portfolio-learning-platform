/**
 * Dependency graph with topological sort and cycle detection.
 */

export class DependencyGraph {
  constructor() {
    this.edges = new Map();      // cell -> Set of cells it depends ON
    this.reverseEdges = new Map(); // cell -> Set of cells that depend on IT
  }

  addCell(id) {
    if (!this.edges.has(id)) this.edges.set(id, new Set());
    if (!this.reverseEdges.has(id)) this.reverseEdges.set(id, new Set());
  }

  setDependencies(cellId, deps) {
    this.addCell(cellId);
    const oldDeps = this.edges.get(cellId);
    for (const dep of oldDeps) {
      this.reverseEdges.get(dep)?.delete(cellId);
    }
    this.edges.set(cellId, new Set(deps));
    for (const dep of deps) {
      this.addCell(dep);
      this.reverseEdges.get(dep).add(cellId);
    }
  }

  getDependents(cellId) {
    return this.reverseEdges.get(cellId) || new Set();
  }

  getDependencies(cellId) {
    return this.edges.get(cellId) || new Set();
  }

  getAllAffected(changedIds) {
    const affected = new Set();
    const queue = [...changedIds];
    while (queue.length > 0) {
      const id = queue.shift();
      for (const dep of this.getDependents(id)) {
        if (!affected.has(dep)) {
          affected.add(dep);
          queue.push(dep);
        }
      }
    }
    return affected;
  }

  detectCycles() {
    const visited = new Set();
    const visiting = new Set();
    const cycles = [];

    const dfs = (node, path) => {
      if (visiting.has(node)) {
        const cycleStart = path.indexOf(node);
        cycles.push(path.slice(cycleStart).concat(node));
        return;
      }
      if (visited.has(node)) return;

      visiting.add(node);
      path.push(node);

      for (const dep of this.getDependencies(node)) {
        dfs(dep, path);
      }

      path.pop();
      visited.add(node);
    };

    for (const node of this.edges.keys()) {
      if (!visited.has(node)) {
        dfs(node, []);
      }
    }
    return cycles;
  }

  topologicalSort(cellIds) {
    const inDegree = new Map();
    const subset = new Set(cellIds);

    for (const id of subset) {
      let deg = 0;
      for (const dep of this.getDependencies(id)) {
        if (subset.has(dep)) deg++;
      }
      inDegree.set(id, deg);
    }

    const queue = [];
    for (const id of subset) {
      if (inDegree.get(id) === 0) queue.push(id);
    }

    const result = [];
    while (queue.length > 0) {
      const node = queue.shift();
      result.push(node);

      for (const dep of this.getDependents(node)) {
        if (!subset.has(dep)) continue;
        const newDeg = inDegree.get(dep) - 1;
        inDegree.set(dep, newDeg);
        if (newDeg === 0) queue.push(dep);
      }
    }
    return result;
  }

  removeCell(id) {
    const deps = this.edges.get(id) || new Set();
    for (const dep of deps) {
      this.reverseEdges.get(dep)?.delete(id);
    }
    this.edges.delete(id);

    const dependents = this.reverseEdges.get(id) || new Set();
    for (const d of dependents) {
      this.edges.get(d)?.delete(id);
    }
    this.reverseEdges.delete(id);
  }
}
