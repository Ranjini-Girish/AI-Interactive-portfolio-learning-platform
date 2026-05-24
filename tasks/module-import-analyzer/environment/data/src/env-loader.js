import { validateString, validateNumber } from './validators';
export function loadEnv() { return { port: validateNumber(process.env.PORT) }; }
export function parseEnvFile(path) { return validateString(path); }
