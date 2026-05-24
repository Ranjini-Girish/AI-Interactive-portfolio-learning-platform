import { log } from './logger.js';

export class EventBus {
  constructor() {
    this.listeners = new Map();
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  emit(event, data) {
    const handlers = this.listeners.get(event) || [];
    handlers.forEach(h => h(data));
  }

  off(event, callback) {
    const handlers = this.listeners.get(event) || [];
    this.listeners.set(event, handlers.filter(h => h !== callback));
  }
}

export function createEvent(name, payload = {}) {
  return { name, payload, timestamp: Date.now() };
}

export const EVENT_TYPES = ['request', 'response', 'error', 'auth'];
