'use strict';

// Commit DAG traversal and depth computation.

/**
 * Build an adjacency map from commit data.
 * @param {Object[]} commits
 * @returns {Map<string, Object>}
 */
function buildCommitMap(commits) {
  // TODO
  return new Map();
}

/**
 * Compute the depth of every commit in the DAG.
 * @param {Map<string, Object>} commitMap
 * @returns {Object<string, number>}
 */
function computeDepths(commitMap) {
  // TODO
  return {};
}

module.exports = { buildCommitMap, computeDepths };
