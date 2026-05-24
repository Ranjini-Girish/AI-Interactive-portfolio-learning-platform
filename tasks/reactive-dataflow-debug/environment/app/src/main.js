/**
 * Entry point: loads configuration and data, runs the reactive dataflow
 * engine through a sequence of operations, and writes results to output.
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { Engine } from './engine.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const APP_ROOT = join(__dirname, '..');
const DATA_DIR = join(APP_ROOT, 'data');
const OUTPUT_DIR = join(APP_ROOT, 'output');

function loadJSON(filename) {
  const raw = readFileSync(join(DATA_DIR, filename), 'utf-8');
  return JSON.parse(raw);
}

function roundValue(val, precision) {
  if (val === null || val === undefined) return null;
  if (typeof val !== 'number') return val;
  return parseFloat(val.toFixed(precision));
}

function run() {
  const config = loadJSON('config.json');
  const initialState = loadJSON('initial_state.json');
  const updateSequence = loadJSON('update_sequence.json');

  const engine = new Engine(config);

  for (const [id, def] of Object.entries(initialState.cells)) {
    engine.addCell(id, def);
  }

  const results = {
    initial_snapshot: {},
    updates: [],
    final_values: {},
    cycles_detected: [],
    recalc_counts: {},
    errors: {},
    recalculation_order: [],
  };

  const state = engine.getState();
  for (const [id, val] of Object.entries(state)) {
    results.initial_snapshot[id] = roundValue(val, config.precision);
  }

  for (let i = 0; i < updateSequence.updates.length; i++) {
    const update = updateSequence.updates[i];
    const auditBefore = engine.getAudit().length;

    if (update.type === 'batch') {
      engine.batchUpdate(update.changes);
    } else if (update.type === 'formula') {
      engine.updateCell(update.cell, { formula: update.formula });
    } else if (update.type === 'value') {
      engine.updateCell(update.cell, { value: update.value });
    }

    const auditAfter = engine.getAudit().length;
    const newEntries = engine.getAudit().slice(auditBefore);

    results.updates.push({
      index: i,
      type: update.type,
      cell: update.cell || null,
      recalculated_cells: newEntries.map(e => e.cell),
    });
  }

  const finalState = engine.getState();
  for (const [id, val] of Object.entries(finalState)) {
    results.final_values[id] = roundValue(val, config.precision);
  }

  results.cycles_detected = engine.detectCycles();
  results.recalc_counts = engine.getRecalcCounts();
  results.errors = engine.getErrors();

  const fullAudit = engine.getAudit();
  results.recalculation_order = fullAudit.map(e => e.cell);

  mkdirSync(OUTPUT_DIR, { recursive: true });
  const outputPath = join(OUTPUT_DIR, 'results.json');
  writeFileSync(outputPath, JSON.stringify(results, null, 2) + '\n', 'utf-8');

  console.log(`Results written to ${outputPath}`);
  console.log(`Cells: ${Object.keys(results.final_values).length}`);
  console.log(`Updates processed: ${results.updates.length}`);
  console.log(`Total recalculations: ${fullAudit.length}`);
  console.log(`Errors: ${Object.keys(results.errors).length}`);
  console.log(`Cycles: ${results.cycles_detected.length}`);
}

run();
