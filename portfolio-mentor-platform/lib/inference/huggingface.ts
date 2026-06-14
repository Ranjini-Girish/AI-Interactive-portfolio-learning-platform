import {
  getEmbedModel,
  getSummaryModel,
  HF_LEGACY_BASE,
  HF_ROUTER_BASE,
} from './config';

type HfSummaryResult =
  | { summary_text: string }
  | Array<{ summary_text: string }>;

type HfEmbedResult = number[] | number[][];

type HfPostResult =
  | { ok: true; data: unknown }
  | { ok: false; status: number; detail: string };

async function hfPost(
  token: string,
  model: string,
  body: unknown,
): Promise<HfPostResult> {
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  const urls = [
    `${HF_ROUTER_BASE}/${model}`,
    `${HF_LEGACY_BASE}/${model}`,
  ];

  let lastStatus = 0;
  let lastDetail = 'Unknown error';

  for (const url of urls) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });

      if (res.ok) {
        return { ok: true, data: await res.json() };
      }

      lastStatus = res.status;
      const text = await res.text();
      try {
        const parsed = JSON.parse(text) as { error?: string; estimated_time?: number };
        lastDetail = parsed.error ?? text.slice(0, 200);
        if (parsed.estimated_time && res.status === 503) {
          lastDetail = `Model loading (${Math.ceil(parsed.estimated_time)}s). Retry in a moment.`;
        }
      } catch {
        lastDetail = text.slice(0, 200) || res.statusText;
      }

      // Auth errors won't succeed on fallback URL — stop early.
      if (res.status === 401 || res.status === 403) {
        break;
      }
    } catch (err) {
      lastDetail = err instanceof Error ? err.message : 'Network error';
    }
  }

  return { ok: false, status: lastStatus, detail: lastDetail };
}

export async function summarizeWithHuggingFace(
  text: string,
  token: string,
  model = getSummaryModel(),
): Promise<string | null> {
  const result = await hfPost(token, model, {
    inputs: text.slice(0, 4000),
    parameters: {
      max_length: 180,
      min_length: 48,
      do_sample: false,
    },
  });

  if (!result.ok) return null;

  const data = result.data as HfSummaryResult;
  if (Array.isArray(data)) {
    return data[0]?.summary_text?.trim() ?? null;
  }
  return data.summary_text?.trim() ?? null;
}

/** Feature-extraction embeddings via HF Inference Providers (hf-inference). */
export async function embedWithHuggingFace(
  texts: string[],
  token: string,
  model = getEmbedModel(),
): Promise<number[][] | null> {
  const trimmed = texts.map((t) => t.slice(0, 2000)).filter(Boolean);
  if (!trimmed.length) return null;

  const result = await hfPost(token, model, {
    inputs: trimmed.length === 1 ? trimmed[0] : trimmed,
    options: { wait_for_model: true },
  });

  if (!result.ok) return null;

  const data = result.data as HfEmbedResult;
  if (Array.isArray(data) && data.length === 0) return null;

  if (typeof data[0] === 'number') {
    return [data as number[]];
  }
  if (Array.isArray(data[0])) {
    return data as number[][];
  }
  return null;
}

export async function checkHfSummarize(token: string): Promise<{ ok: boolean; error: string | null }> {
  const sample =
    'Segment 0 (High value): 120 customers, avg balance $45,000, monthly spend $2,100.';
  const summary = await summarizeWithHuggingFace(sample, token);
  if (summary) return { ok: true, error: null };

  const probe = await hfPost(token, getSummaryModel(), {
    inputs: sample.slice(0, 500),
    parameters: { max_length: 80, min_length: 20, do_sample: false },
  });
  if (!probe.ok) {
    if (probe.status === 401 || probe.status === 403) {
      return {
        ok: false,
        error: 'Token rejected. Use a fine-grained token with “Make calls to Inference Providers”.',
      };
    }
    return { ok: false, error: probe.detail };
  }
  return { ok: false, error: 'Summarization returned empty output.' };
}

export async function checkHfEmbed(
  token: string,
): Promise<{ ok: boolean; error: string | null; dimensions: number | null }> {
  const vectors = await embedWithHuggingFace(['policy coverage test'], token);
  if (vectors?.[0]?.length) {
    return { ok: true, error: null, dimensions: vectors[0].length };
  }

  const probe = await hfPost(token, getEmbedModel(), {
    inputs: 'policy coverage test',
    options: { wait_for_model: true },
  });
  if (!probe.ok) {
    if (probe.status === 401 || probe.status === 403) {
      return {
        ok: false,
        error: 'Token rejected. Use a fine-grained token with “Make calls to Inference Providers”.',
        dimensions: null,
      };
    }
    return { ok: false, error: probe.detail, dimensions: null };
  }
  return { ok: false, error: 'Embedding returned empty output.', dimensions: null };
}
