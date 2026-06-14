import { inferenceCorsHeaders, jsonWithCors } from '@/lib/inference/cors';
import {
  getEmbedModel,
  getHfToken,
  getSummaryModel,
  maskToken,
  type HfServiceCheck,
} from '@/lib/inference/config';
import { checkHfEmbed, checkHfSummarize } from '@/lib/inference/huggingface';
import { getSupabaseServiceKey, getSupabaseUrl, maskUrl } from '@/lib/lab/config';
import { getSupabaseAdmin } from '@/lib/lab/store';

export async function OPTIONS() {
  return new Response(null, { status: 204, headers: inferenceCorsHeaders });
}

async function checkSupabase(): Promise<{
  configured: boolean;
  url_preview: string | null;
  can_write: boolean;
  error: string | null;
}> {
  const url = getSupabaseUrl();
  const key = getSupabaseServiceKey();
  if (!url || !key) {
    return {
      configured: false,
      url_preview: null,
      can_write: false,
      error: 'Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.local or Vercel.',
    };
  }

  const sb = getSupabaseAdmin();
  if (!sb) {
    return {
      configured: true,
      url_preview: maskUrl(url),
      can_write: false,
      error: 'Supabase client failed to initialize.',
    };
  }

  const { error } = await sb.from('lab_runs').select('id').limit(1);
  if (error) {
    return {
      configured: true,
      url_preview: maskUrl(url),
      can_write: false,
      error: error.message.includes('lab_runs')
        ? 'Run supabase/schema.sql in your Supabase SQL Editor first.'
        : error.message,
    };
  }

  return { configured: true, url_preview: maskUrl(url), can_write: true, error: null };
}

async function checkHf(): Promise<HfServiceCheck> {
  const token = getHfToken();
  const summary_model = getSummaryModel();
  const embed_model = getEmbedModel();

  if (!token) {
    return {
      configured: false,
      token_preview: null,
      summary_model,
      embed_model,
      summarize: {
        ok: false,
        error: 'HF_TOKEN not set. Create a token at huggingface.co/settings/tokens.',
      },
      embed: {
        ok: false,
        error: 'HF_TOKEN not set.',
        dimensions: null,
      },
    };
  }

  const [summarize, embed] = await Promise.all([
    checkHfSummarize(token),
    checkHfEmbed(token),
  ]);

  return {
    configured: true,
    token_preview: maskToken(token),
    summary_model,
    embed_model,
    summarize,
    embed,
  };
}

export async function GET() {
  const [huggingface, supabase] = await Promise.all([checkHf(), checkSupabase()]);

  const hfReady = huggingface.summarize.ok && huggingface.embed.ok;
  const supabaseReady = supabase.can_write;

  return jsonWithCors({
    ok: hfReady,
    huggingface,
    supabase,
    app_url: process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3200',
    ready: {
      rag_lab: hfReady,
      p01_summarize: huggingface.summarize.ok,
      proof_links: supabaseReady,
    },
  });
}
