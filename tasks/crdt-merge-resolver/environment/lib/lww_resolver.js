"use strict";

/**
 * Last-Writer-Wins register resolver.
 *
 * Resolves the final state of each key from the merged operation log.
 */

/**
 * Resolve final state for all keys using LWW semantics.
 * @param {Array} mergedOps - Operations sorted in total order
 * @param {Object} config - Merge configuration
 * @returns {Array} Array of key_state objects (sorted by key)
 */
function resolveStates(mergedOps, config) {
  // TODO: Implement LWW resolution with tombstone/resurrection handling
  throw new Error("Not implemented");
}

module.exports = { resolveStates };
