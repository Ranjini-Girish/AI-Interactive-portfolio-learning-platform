import { query, transaction } from '../db';
import { Logger } from '../logger';
import { validateString } from '../validators';
export function handleProduct(req) { return transaction(() => query('SELECT * FROM products')); }
