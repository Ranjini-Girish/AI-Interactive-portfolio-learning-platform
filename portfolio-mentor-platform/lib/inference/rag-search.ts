import { cosineSimilarity } from './embed-local';
import { embedTexts } from './embed';
import type { RagSearchRequest, RagSearchResponse } from './types';

export async function searchDocuments(body: RagSearchRequest): Promise<RagSearchResponse> {
  const topK = Math.min(body.top_k ?? 3, body.documents.length);
  if (!body.query.trim() || !body.documents.length || topK < 1) {
    return { hits: [], model: null, provider: 'local' };
  }

  const texts = [body.query, ...body.documents.map((d) => d.text)];
  const embedded = await embedTexts(texts);
  const [queryVec, ...docVecs] = embedded.embeddings;

  const scored = body.documents.map((doc, i) => ({
    id: doc.id,
    text: doc.text,
    score: cosineSimilarity(queryVec, docVecs[i]),
  }));

  scored.sort((a, b) => b.score - a.score);

  return {
    hits: scored.slice(0, topK),
    model: embedded.model,
    provider: embedded.provider,
  };
}
