import { readFileSync } from "fs";

export function loadEvents(path) {
  return JSON.parse(readFileSync(path, "utf-8"));
}

export function sortEvents(events) {
  return [...events].sort((a, b) => {
    if (a.timestamp !== b.timestamp) return a.timestamp - b.timestamp;
    return b.event_id.localeCompare(a.event_id);
  });
}
