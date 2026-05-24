import defaults from './defaults';
import { loadEnv } from './env-loader';
export function loadConfig() { return { ...defaults, ...loadEnv() }; }
export function getConfigValue(key) { return defaults[key]; }
export * from './defaults';
