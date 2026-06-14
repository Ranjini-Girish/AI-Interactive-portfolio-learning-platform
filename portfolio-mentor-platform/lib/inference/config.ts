export const HF_SUMMARY_MODEL_DEFAULT = 'facebook/bart-large-cnn';
export const HF_EMBED_MODEL_DEFAULT = 'sentence-transformers/all-MiniLM-L6-v2';

export const HF_ROUTER_BASE = 'https://router.huggingface.co/hf-inference/models';
export const HF_LEGACY_BASE = 'https://api-inference.huggingface.co/models';

export type HfServiceCheck = {
  configured: boolean;
  token_preview: string | null;
  summary_model: string;
  embed_model: string;
  summarize: { ok: boolean; error: string | null };
  embed: { ok: boolean; error: string | null; dimensions: number | null };
};

export function getHfToken(): string | null {
  const token = process.env.HF_TOKEN?.trim();
  if (!token || !token.startsWith('hf_')) return null;
  return token;
}

export function getSummaryModel(): string {
  return process.env.HF_SUMMARY_MODEL?.trim() || HF_SUMMARY_MODEL_DEFAULT;
}

export function getEmbedModel(): string {
  return process.env.HF_EMBED_MODEL?.trim() || HF_EMBED_MODEL_DEFAULT;
}

export function maskToken(token: string): string {
  if (token.length <= 11) return 'hf_***';
  return `${token.slice(0, 7)}…${token.slice(-4)}`;
}
