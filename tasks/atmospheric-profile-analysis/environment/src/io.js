/**
 * Data I/O utilities for loading sounding files and writing output.
 */
const fs = require('fs');
const path = require('path');

function loadJSON(filepath) {
  return JSON.parse(fs.readFileSync(filepath, 'utf-8'));
}

function writeJSON(filepath, data) {
  // TODO: Implement with correct formatting
  fs.writeFileSync(filepath, JSON.stringify(data));
}

function listSoundings(dir) {
  return fs.readdirSync(dir).filter(f => f.endsWith('.json')).sort();
}

module.exports = { loadJSON, writeJSON, listSoundings };
