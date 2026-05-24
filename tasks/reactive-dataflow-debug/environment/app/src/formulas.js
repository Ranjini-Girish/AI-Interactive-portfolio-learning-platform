/**
 * Formula parser and evaluator for the reactive dataflow engine.
 * Supports: arithmetic, cell references, and built-in functions.
 */

const FUNCTIONS = ['SUM', 'AVG', 'MIN', 'MAX', 'IF', 'ABS', 'ROUND', 'COUNT', 'COUNTIF'];

class FormulaError extends Error {
  constructor(message, type = 'EVAL') {
    super(message);
    this.type = type;
  }
}

export function extractDependencies(formula) {
  if (formula === null || formula === undefined) return [];
  const str = String(formula);
  const cellRefPattern = /\b([A-Z][A-Z0-9]*[0-9]+)\b/g;
  const deps = new Set();
  let match;
  while ((match = cellRefPattern.exec(str)) !== null) {
    deps.add(match[1]);
  }
  return [...deps];
}

function tokenize(formula) {
  const tokens = [];
  let i = 0;
  const s = formula.trim();

  while (i < s.length) {
    if (/\s/.test(s[i])) { i++; continue; }

    if (/[0-9]/.test(s[i]) || (s[i] === '-' && (tokens.length === 0 || /[,(+\-*/><!=]/.test(tokens[tokens.length - 1]?.value)))) {
      let num = '';
      if (s[i] === '-') { num += s[i]; i++; }
      while (i < s.length && /[0-9.]/.test(s[i])) { num += s[i]; i++; }
      tokens.push({ type: 'number', value: num });
      continue;
    }

    if (/[A-Z]/.test(s[i])) {
      let id = '';
      while (i < s.length && /[A-Z0-9_]/.test(s[i])) { id += s[i]; i++; }
      if (FUNCTIONS.includes(id)) {
        tokens.push({ type: 'function', value: id });
      } else {
        tokens.push({ type: 'cellref', value: id });
      }
      continue;
    }

    if ('+-*/(),'.includes(s[i])) {
      tokens.push({ type: 'operator', value: s[i] });
      i++;
      continue;
    }

    if ('><!='.includes(s[i])) {
      let op = s[i]; i++;
      if (i < s.length && s[i] === '=') { op += s[i]; i++; }
      tokens.push({ type: 'comparator', value: op });
      continue;
    }

    i++;
  }
  return tokens;
}

function parseExpression(tokens, pos) {
  let [left, nextPos] = parseTerm(tokens, pos);
  while (nextPos < tokens.length &&
    tokens[nextPos].type === 'operator' && '+-'.includes(tokens[nextPos].value)) {
    const op = tokens[nextPos].value;
    nextPos++;
    let [right, p] = parseTerm(tokens, nextPos);
    nextPos = p;
    left = { type: 'binary', op, left, right };
  }

  if (nextPos < tokens.length && tokens[nextPos].type === 'comparator') {
    const op = tokens[nextPos].value;
    nextPos++;
    let [right, p] = parseExpression(tokens, nextPos);
    nextPos = p;
    left = { type: 'comparison', op, left, right };
  }

  return [left, nextPos];
}

function parseTerm(tokens, pos) {
  let [left, nextPos] = parseFactor(tokens, pos);
  while (nextPos < tokens.length &&
    tokens[nextPos].type === 'operator' && '*/'.includes(tokens[nextPos].value)) {
    const op = tokens[nextPos].value;
    nextPos++;
    let [right, p] = parseFactor(tokens, nextPos);
    nextPos = p;
    left = { type: 'binary', op, left, right };
  }
  return [left, nextPos];
}

function parseFactor(tokens, pos) {
  if (pos >= tokens.length) throw new FormulaError('Unexpected end of formula');
  const tok = tokens[pos];

  if (tok.type === 'number') {
    return [{ type: 'literal', value: parseFloat(tok.value) }, pos + 1];
  }

  if (tok.type === 'cellref') {
    return [{ type: 'ref', id: tok.value }, pos + 1];
  }

  if (tok.type === 'function') {
    const fname = tok.value;
    pos++;
    if (tokens[pos]?.value !== '(') throw new FormulaError(`Expected ( after ${fname}`);
    pos++;
    const args = [];
    while (pos < tokens.length && tokens[pos].value !== ')') {
      const [arg, p] = parseExpression(tokens, pos);
      args.push(arg);
      pos = p;
      if (tokens[pos]?.value === ',') pos++;
    }
    if (tokens[pos]?.value !== ')') throw new FormulaError(`Missing ) for ${fname}`);
    pos++;
    return [{ type: 'call', name: fname, args }, pos];
  }

  if (tok.value === '(') {
    pos++;
    const [expr, p] = parseExpression(tokens, pos);
    if (tokens[p]?.value !== ')') throw new FormulaError('Missing )');
    return [expr, p + 1];
  }

  throw new FormulaError(`Unexpected token: ${JSON.stringify(tok)}`);
}

export function parse(formula) {
  const tokens = tokenize(formula);
  if (tokens.length === 0) return { type: 'literal', value: 0 };
  const [ast, _pos] = parseExpression(tokens, 0);
  return ast;
}

export function evaluate(ast, getCellValue, config = {}) {
  const precision = config.precision ?? 6;

  function eval_(node) {
    switch (node.type) {
      case 'literal':
        return node.value;

      case 'ref': {
        const val = getCellValue(node.id);
        if (val instanceof Error) throw val;
        return val;
      }

      case 'binary': {
        const l = eval_(node.left);
        const r = eval_(node.right);
        switch (node.op) {
          case '+': return l + r;
          case '-': return l - r;
          case '*': return l * r;
          case '/': {
            if (r === 0) throw new FormulaError('Division by zero', 'DIV0');
            const result = l / r;
            return parseFloat(result.toFixed(precision));
          }
        }
        break;
      }

      case 'comparison': {
        const l = eval_(node.left);
        const r = eval_(node.right);
        switch (node.op) {
          case '>': return l > r ? 1 : 0;
          case '<': return l < r ? 1 : 0;
          case '>=': return l >= r ? 1 : 0;
          case '<=': return l <= r ? 1 : 0;
          case '==': return l === r ? 1 : 0;
          case '!=': return l !== r ? 1 : 0;
        }
        break;
      }

      case 'call':
        return evalFunction(node.name, node.args);
    }
    throw new FormulaError(`Unknown node type: ${node.type}`);
  }

  function evalFunction(name, args) {
    switch (name) {
      case 'SUM': {
        let total = 0;
        for (const arg of args) total += eval_(arg);
        return total;
      }

      case 'AVG': {
        if (args.length === 0) throw new FormulaError('AVG requires at least one argument');
        let total = 0;
        for (const arg of args) total += eval_(arg);
        return total / args.length;
      }

      case 'MIN': {
        const vals = args.map(a => eval_(a));
        return Math.min(...vals);
      }

      case 'MAX': {
        const vals = args.map(a => eval_(a));
        return Math.max(...vals);
      }

      case 'IF': {
        if (args.length < 3) throw new FormulaError('IF requires 3 arguments');
        const condition = eval_(args[0]);
        const thenVal = eval_(args[1]);
        const elseVal = eval_(args[2]);
        return condition ? thenVal : elseVal;
      }

      case 'ABS': {
        if (args.length !== 1) throw new FormulaError('ABS requires 1 argument');
        return Math.abs(eval_(args[0]));
      }

      case 'ROUND': {
        if (args.length < 1) throw new FormulaError('ROUND requires at least 1 argument');
        const val = eval_(args[0]);
        const places = args.length > 1 ? eval_(args[1]) : 0;
        const factor = Math.pow(10, places);
        return Math.round(val * factor) / factor;
      }

      case 'COUNT': {
        return args.length;
      }

      case 'COUNTIF': {
        if (args.length < 2) throw new FormulaError('COUNTIF requires at least 2 args');
        const threshold = eval_(args[args.length - 1]);
        let count = 0;
        for (let i = 0; i < args.length - 1; i++) {
          try {
            const val = eval_(args[i]);
            if (val > threshold) count++;
          } catch (e) {
            // skip error cells
          }
        }
        return count;
      }

      default:
        throw new FormulaError(`Unknown function: ${name}`);
    }
  }

  return eval_(ast);
}
