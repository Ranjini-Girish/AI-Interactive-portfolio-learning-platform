import { Logger } from './logger';
export class EventBus {
    constructor() { this.handlers = {}; }
    on(event, fn) { this.handlers[event] = fn; }
    emit(event, data) { Logger.info(event); this.handlers[event]?.(data); }
}
export function createBus() { return new EventBus(); }
export { default as BusAuth } from './auth';
