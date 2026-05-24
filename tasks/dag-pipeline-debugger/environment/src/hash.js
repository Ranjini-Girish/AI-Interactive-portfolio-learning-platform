import { createHash } from "crypto";

export function computeIntegrityHash(processed) {
  const lines = [];

  for (const evt of processed) {
    const sinks = [...evt.sinkResults].sort(
      (a, b) => b.sinkId.localeCompare(a.sinkId)
    );
    for (const sr of sinks) {
      lines.push(
        `${evt.eventId}|${sr.sinkId}|${sr.endToEndLatency}|${evt.priority}`
      );
    }
  }

  const canonical = lines.join("\n");
  return createHash("sha256").update(canonical, "utf-8").digest("hex");
}
