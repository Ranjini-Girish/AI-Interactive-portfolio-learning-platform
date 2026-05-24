/**
 * Core reactive dataflow engine. Manages cells, tracks dependencies,
 * and coordinates recalculation when values change.
 */

import { DependencyGraph } from './graph.js';
import { parse, evaluate, extractDependencies } from './formulas.js';

export class Engine {
  constructor(config = {}) {
    this.config = {
      precision: config.precision ?? 6,
      maxIterations: config.max_iterations ?? 1000,
      auditEnabled: config.audit_enabled ?? true,
    };
    this.cells = new Map();
    this.graph = new DependencyGraph();
    this.audit = [];
    this.recalcCounts = new Map();
    this.errorCells = new Map();
  }

  addCell(id, definition) {
    this.graph.addCell(id);
    this.cells.set(id, {
      id,
      formula: definition.formula || null,
      value: definition.value ?? null,
      isFormula: !!definition.formula,
    });
    this.recalcCounts.set(id, 0);

    if (definition.formula) {
      const deps = extractDependencies(definition.formula);
      this.graph.setDependencies(id, deps);
      this._evaluateCell(id);
    }
  }

  updateCell(id, newDefinition) {
    const cell = this.cells.get(id);

    if (newDefinition.formula !== undefined) {
      if (cell && cell.isFormula) {
        cell.formula = newDefinition.formula;
        cell.isFormula = true;
        cell.value = null;
      } else {
        this.cells.set(id, {
          id,
          formula: newDefinition.formula,
          value: null,
          isFormula: true,
        });
        this.graph.addCell(id);
        const deps = extractDependencies(newDefinition.formula);
        this.graph.setDependencies(id, deps);
      }
      this._evaluateCell(id);
      this._recalculateDependents(id);
    } else if (newDefinition.value !== undefined) {
      if (!cell) {
        this.cells.set(id, { id, formula: null, value: newDefinition.value, isFormula: false });
        this.graph.addCell(id);
        this.recalcCounts.set(id, 0);
      } else {
        cell.value = newDefinition.value;
        cell.isFormula = false;
        cell.formula = null;
      }
      this._recalculateDependents(id);
    }
  }

  batchUpdate(changes) {
    for (const change of changes) {
      if (change.formula !== undefined) {
        const cell = this.cells.get(change.cell);
        if (cell && cell.isFormula) {
          cell.formula = change.formula;
        } else {
          this.cells.set(change.cell, {
            id: change.cell,
            formula: change.formula,
            value: null,
            isFormula: true,
          });
          this.graph.addCell(change.cell);
          const deps = extractDependencies(change.formula);
          this.graph.setDependencies(change.cell, deps);
        }
      } else {
        const cell = this.cells.get(change.cell);
        if (!cell) {
          this.cells.set(change.cell, {
            id: change.cell, formula: null, value: change.value, isFormula: false
          });
          this.graph.addCell(change.cell);
          this.recalcCounts.set(change.cell, 0);
        } else {
          cell.value = change.value;
          cell.isFormula = false;
          cell.formula = null;
        }
      }
    }

    const changedIds = changes.map(c => c.cell);
    const affected = this.graph.getAllAffected(changedIds);

    for (const id of changedIds) {
      if (this.cells.get(id)?.isFormula) {
        affected.add(id);
      }
    }

    this._recalculateSet(affected);
  }

  _recalculateDependents(changedId) {
    const affected = this.graph.getAllAffected([changedId]);
    this._recalculateSet(affected);
  }

  _recalculateSet(affected) {
    if (affected.size === 0) return;

    const order = this.graph.topologicalSort(affected);

    for (const id of order) {
      this._evaluateCell(id);
    }
  }

  _evaluateCell(id) {
    const cell = this.cells.get(id);
    if (!cell || !cell.isFormula) return;

    try {
      const ast = parse(cell.formula);
      const value = evaluate(ast, (refId) => {
        const refCell = this.cells.get(refId);
        if (!refCell) throw new Error(`Reference to undefined cell: ${refId}`);
        if (this.errorCells.has(refId)) {
          throw this.errorCells.get(refId);
        }
        return refCell.value;
      }, this.config);

      cell.value = value;
      this.errorCells.delete(id);
    } catch (e) {
      cell.value = null;
      this.errorCells.set(id, e);
    }

    const count = (this.recalcCounts.get(id) || 0) + 1;
    this.recalcCounts.set(id, count);

    if (this.config.auditEnabled) {
      this.audit.push({ cell: id, value: cell.value, recalcNumber: count });
    }
  }

  getCellValue(id) {
    const cell = this.cells.get(id);
    return cell ? cell.value : undefined;
  }

  getState() {
    const finalValues = {};
    for (const [id, cell] of this.cells) {
      if (this.errorCells.has(id)) {
        finalValues[id] = null;
      } else {
        finalValues[id] = cell.value;
      }
    }
    return finalValues;
  }

  getRecalcCounts() {
    const counts = {};
    for (const [id, count] of this.recalcCounts) {
      counts[id] = count;
    }
    return counts;
  }

  getErrors() {
    const errors = {};
    for (const [id, err] of this.errorCells) {
      errors[id] = { message: err.message, type: err.type || 'ERROR' };
    }
    return errors;
  }

  getAudit() {
    return this.audit;
  }

  detectCycles() {
    return this.graph.detectCycles();
  }
}
