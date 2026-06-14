import type { SummarizeSegmentsRequest, SummarizeSegmentsResponse } from './types';

export function buildLocalSegmentSummary(
  body: SummarizeSegmentsRequest,
): SummarizeSegmentsResponse {
  const { centroids, metrics } = body.segments;
  const sorted = [...centroids].sort((a, b) => b.monthly_spend - a.monthly_spend);
  const top = sorted[0];
  const low = sorted[sorted.length - 1];

  const summary =
    `We identified ${metrics.k} customer groups (silhouette ${metrics.silhouette_score.toFixed(2)}). ` +
    `${top.segment_name} has the highest average monthly spend (~$${Math.round(top.monthly_spend).toLocaleString()}), ` +
    `while ${low.segment_name} spends less (~$${Math.round(low.monthly_spend).toLocaleString()}). ` +
    `Marketing should prioritize high-spend segments for premium offers and use tailored retention for lower-activity groups.`;

  const bullets = sorted.map(
    (c) =>
      `${c.segment_name}: ~$${Math.round(c.monthly_spend).toLocaleString()}/mo spend, ` +
      `$${Math.round(c.avg_balance).toLocaleString()} avg balance`,
  );

  return {
    summary,
    bullets,
    source: 'local',
    model: null,
    provider: 'local',
  };
}
