'use strict';

// Author aggregation with mailmap normalization.

/**
 * Normalize an email using mailmap aliases (case-insensitive).
 * @param {string} email
 * @param {Object} mailmap
 * @returns {string}
 */
function normalizeEmail(email, mailmap) {
  // TODO
  return email.toLowerCase();
}

/**
 * Aggregate per-author statistics from commits.
 * @param {Object[]} commits
 * @param {Object} mailmap
 * @returns {Object[]}
 */
function aggregateAuthors(commits, mailmap) {
  // TODO
  return [];
}

module.exports = { normalizeEmail, aggregateAuthors };
