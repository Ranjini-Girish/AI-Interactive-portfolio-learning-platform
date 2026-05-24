/**
 * Custom error types for the reactive dataflow engine.
 */

export class FormulaError extends Error {
  constructor(message, type = 'EVAL') {
    super(message);
    this.name = 'FormulaError';
    this.type = type;
  }
}

export class CycleError extends Error {
  constructor(cellIds) {
    super(`Circular dependency detected: ${cellIds.join(' -> ')}`);
    this.name = 'CycleError';
    this.type = 'CYCLE';
    this.cellIds = cellIds;
  }
}

export class ReferenceError extends Error {
  constructor(cellId) {
    super(`Reference to undefined cell: ${cellId}`);
    this.name = 'ReferenceError';
    this.type = 'REF';
    this.cellId = cellId;
  }
}
