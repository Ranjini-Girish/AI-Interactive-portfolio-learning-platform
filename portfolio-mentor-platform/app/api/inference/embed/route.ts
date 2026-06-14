import { inferenceCorsHeaders, jsonWithCors } from '@/lib/inference/cors';
import { embedTexts } from '@/lib/inference/embed';
import type { EmbedRequest } from '@/lib/inference/types';

export async function OPTIONS() {
  return new Response(null, { status: 204, headers: inferenceCorsHeaders });
}

export async function POST(request: Request) {
  const body = (await request.json()) as EmbedRequest;

  if (!body.texts?.length) {
    return jsonWithCors({ error: 'texts array required' }, { status: 400 });
  }
  if (body.texts.length > 32) {
    return jsonWithCors({ error: 'Maximum 32 texts per request' }, { status: 400 });
  }

  const result = await embedTexts(body.texts);
  return jsonWithCors(result);
}
