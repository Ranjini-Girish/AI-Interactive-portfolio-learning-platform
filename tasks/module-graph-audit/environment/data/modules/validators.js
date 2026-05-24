import { FIELD_LIMITS, PATTERNS } from './constants.js';
import { ValidationError } from './errors.js';

export function validateRequest(schema, data) {
  for (const [field, rules] of Object.entries(schema)) {
    if (rules.required && !(field in data)) {
      throw new ValidationError(`Missing required field: ${field}`);
    }
    if (field in data) {
      validateField(field, data[field]);
    }
  }
  return true;
}

export function validateField(name, value) {
  if (typeof value === 'string') {
    const limit = FIELD_LIMITS[name];
    if (limit && value.length > limit) {
      throw new ValidationError(`${name} exceeds max length ${limit}`);
    }
  }
  return value;
}

export function sanitize(input) {
  if (typeof input !== 'string') return input;
  return input.replace(/[<>&"']/g, (ch) => {
    const map = { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' };
    return map[ch];
  });
}
