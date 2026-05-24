import { formatLog, formatError as fmtErr } from './formatters';
import { loadConfig } from './config';
export class Logger {
    static info(msg) { console.log(formatLog(msg)); }
    static error(msg) { console.error(fmtErr(msg)); }
    static close() {}
}
export function createLogger(name) { return new Logger(name); }
export { formatLog } from './formatters';
