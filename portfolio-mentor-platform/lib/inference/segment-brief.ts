import type { SummarizeSegmentsRequest } from './types';

/** Plain-text brief for HF summarization or local fallback. */
export function buildSegmentBrief(body: SummarizeSegmentsRequest): string {
  const company = body.company ?? 'the bank';
  const { centroids, metrics } = body.segments;
  const lines = [
    `Customer segmentation analysis for ${company}.`,
    `We grouped customers into ${metrics.k} segments using machine learning clustering.`,
    `Model quality (silhouette score): ${metrics.silhouette_score.toFixed(3)} on a scale where higher is better.`,
    '',
    'Segment profiles:',
  ];

  for (const c of centroids) {
    lines.push(
      `- ${c.segment_name}: average monthly spend $${Math.round(c.monthly_spend).toLocaleString()}, ` +
        `average balance $${Math.round(c.avg_balance).toLocaleString()}, ` +
        `typical transaction count ${Math.round(c.txn_count)}.`,
    );
  }

  lines.push(
    '',
    'Write a short stakeholder summary recommending which segments matter for marketing and why.',
  );
  return lines.join('\n');
}
