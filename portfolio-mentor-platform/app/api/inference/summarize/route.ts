import { inferenceCorsHeaders, jsonWithCors } from '@/lib/inference/cors';
import { buildSegmentBrief } from '@/lib/inference/segment-brief';
import { summarizeWithHuggingFace } from '@/lib/inference/huggingface';
import { buildLocalSegmentSummary } from '@/lib/inference/local-summary';
import type { SummarizeSegmentsRequest } from '@/lib/inference/types';

export async function OPTIONS() {
  return new Response(null, { status: 204, headers: inferenceCorsHeaders });
}

export async function POST(request: Request) {
  const body = (await request.json()) as SummarizeSegmentsRequest;

  if (!body.segments?.centroids?.length || !body.segments?.metrics) {
    return jsonWithCors({ error: 'Missing segment data' }, { status: 400 });
  }

  const brief = buildSegmentBrief(body);
  const local = buildLocalSegmentSummary(body);
  const token = process.env.HF_TOKEN;

  if (token) {
    const model = process.env.HF_SUMMARY_MODEL ?? 'facebook/bart-large-cnn';
    const hfText = await summarizeWithHuggingFace(brief, token, model);
    if (hfText) {
      return jsonWithCors({
        summary: hfText,
        bullets: local.bullets,
        source: 'huggingface',
        model,
        provider: 'huggingface',
      });
    }
  }

  return jsonWithCors(local);
}