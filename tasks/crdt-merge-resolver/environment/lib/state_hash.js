"use strict";

/**
 * State hash computation for the CRDT merge engine.
 */

const crypto = require("crypto");

/**
 * Compute SHA-256 hash of the final merged state.
 * @param {Array} keyStates - Resolved key states
 * @param {Object} config - Merge configuration
 * @returns {string} Hex-encoded SHA-256 hash
 */
function computeStateHash(keyStates, config) {
  // TODO: Implement state hash computation
  // Must match the exact protocol defined in crdt_semantics.md
  throw new Error("Not implemented");
}

module.exports = { computeStateHash };
