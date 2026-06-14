import { inferenceCorsHeaders, jsonWithCors } from '@/lib/inference/cors';
import { searchDocuments } from '@/lib/inference/rag-search';
import type { RagSearchRequest } from '@/lib/inference/types';

export async function OPTIONS() {
  return new Response(null, { status: 204, headers: inferenceCorsHeaders });
}

export async function POST(request: Request) {
  const body = (await request.json()) as RagSearchRequest;

  if (!body.query?.trim()) {
    return jsonWithCors({ error: 'query required' }, { status: 400 });
  }
  if (!body.documents?.length) {
    return jsonWithCors({ error: 'documents required' }, { status: 400 });
  }
  if (body.documents.length > 50) {
    return jsonWithCors({ error: 'Maximum 50 documents' }, { status: 400 });
  }

  const result = await searchDocuments(body);
  return jsonWithCors(result);
}
