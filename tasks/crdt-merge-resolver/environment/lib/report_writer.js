"use strict";

/**
 * Report writer - formats and writes the merge report JSON.
 *
 * Ensures:
 * - All JSON keys sorted alphabetically at every level
 * - 2-space indentation
 * - Trailing newline
 */

const fs = require("fs");
const path = require("path");

/**
 * Write the merge report to the output file.
 * @param {Object} report - The complete merge report object
 * @param {string} outputPath - Path to write the report
 */
function writeReport(report, outputPath) {
  // TODO: Implement with sorted keys and proper formatting
  throw new Error("Not implemented");
}

module.exports = { writeReport };
