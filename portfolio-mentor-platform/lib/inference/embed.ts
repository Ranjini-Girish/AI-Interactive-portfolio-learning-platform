import { embedLocally } from './embed-local';
import { embedWithHuggingFace } from './huggingface';
import type { EmbedResponse } from './types';

export async function embedTexts(texts: string[]): Promise<EmbedResponse> {
  const token = process.env.HF_TOKEN;
  const model = process.env.HF_EMBED_MODEL ?? 'sentence-transformers/all-MiniLM-L6-v2';

  if (token) {
    const hf = await embedWithHuggingFace(texts, token, model);
    if (hf?.length) {
      return {
        embeddings: hf,
        model,
        provider: 'huggingface',
        dimensions: hf[0]?.length ?? 0,
      };
    }
  }

  const local = embedLocally(texts);
  return {
    embeddings: local,
    model: null,
    provider: 'local',
    dimensions: local[0]?.length ?? 0,
  };
}
