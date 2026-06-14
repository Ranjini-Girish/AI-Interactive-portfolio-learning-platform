'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

type StatusPayload = {
  ok: boolean;
  huggingface: {
    configured: boolean;
    token_preview: string | null;
    summary_model: string;
    embed_model: string;
    summarize: { ok: boolean; error: string | null };
    embed: { ok: boolean; error: string | null; dimensions: number | null };
  };
  supabase: {
    configured: boolean;
    url_preview: string | null;
    can_write: boolean;
    error: string | null;
  };
  ready: {
    rag_lab: boolean;
    p01_summarize: boolean;
    proof_links: boolean;
  };
};

const HF_STEPS = [
  {
    title: 'Create a Hugging Face account',
    body: (
      <>
        Go to{' '}
        <a
          href="https://huggingface.co/join"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--accent)] hover:underline"
        >
          huggingface.co/join
        </a>{' '}
        and sign up. Confirm your email — the &quot;New token&quot; button stays disabled until
        verification completes.
      </>
    ),
  },
  {
    title: 'Open Access Tokens settings',
    body: (
      <>
        Profile menu → Settings →{' '}
        <a
          href="https://huggingface.co/settings/tokens"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--accent)] hover:underline"
        >
          Access Tokens
        </a>
        . Or go directly to{' '}
        <code className="rounded bg-[var(--bg)] px-1">huggingface.co/settings/tokens</code>.
      </>
    ),
  },
  {
    title: 'Create a fine-grained token',
    body: (
      <>
        Click <strong>New token</strong> → choose <strong>Fine-grained</strong>. Name it e.g.{' '}
        <code className="rounded bg-[var(--bg)] px-1">portfolio-lab-local</code>.
      </>
    ),
  },
  {
    title: 'Enable Inference Providers permission',
    body: (
      <>
        Under permissions, turn on{' '}
        <strong>Make calls to Inference Providers</strong>. This is required for summarization (
        <code className="rounded bg-[var(--bg)] px-1">facebook/bart-large-cnn</code>) and embeddings (
        <code className="rounded bg-[var(--bg)] px-1">sentence-transformers/all-MiniLM-L6-v2</code>
        ). Read access to public models is included.
      </>
    ),
  },
  {
    title: 'Copy the token once',
    body: (
      <>
        Click <strong>Create token</strong>. Copy the value starting with{' '}
        <code className="rounded bg-[var(--bg)] px-1">hf_</code> immediately — Hugging Face shows
        the full token only once.
      </>
    ),
  },
  {
    title: 'Add to .env.local (local) or Vercel (production)',
    body: (
      <>
        Paste into{' '}
        <code className="rounded bg-[var(--bg)] px-1">portfolio-mentor-platform/.env.local</code>{' '}
        or run the setup script below. Never commit the token to git.
      </>
    ),
  },
];

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        ok
          ? 'bg-emerald-500/15 text-emerald-400'
          : 'bg-amber-500/15 text-amber-300'
      }`}
    >
      {ok ? '✓' : '○'} {label}
    </span>
  );
}

export default function LabSetupPage() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/inference/status');
      if (!res.ok) throw new Error('Status check failed');
      setStatus(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach status API');
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const envBlock = `# portfolio-mentor-platform/.env.local
HF_TOKEN=hf_paste_your_token_here
HF_SUMMARY_MODEL=facebook/bart-large-cnn
HF_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Optional — shareable proof links (see supabase/schema.sql)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_APP_URL=http://localhost:3200`;

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10 sm:px-6">
      <header>
        <p className="text-sm font-medium text-[var(--accent)]">Lab infrastructure</p>
        <h1 className="mt-2 text-3xl font-bold">Connect Hugging Face &amp; Supabase</h1>
        <p className="mt-3 text-[var(--muted)] leading-relaxed">
          Real lab features — stakeholder summaries, semantic RAG search, and shareable proof
          links — need API keys on the server. Follow the steps below, then verify with the live
          status check.
        </p>
      </header>

      <section className="card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Live status</h2>
          <button type="button" className="btn-primary text-sm" disabled={loading} onClick={refresh}>
            {loading ? 'Checking…' : 'Re-check connection'}
          </button>
        </div>
        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
        {status && (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap gap-2">
              <StatusPill ok={status.ready.p01_summarize} label="P01 summarize (HF)" />
              <StatusPill ok={status.ready.rag_lab} label="RAG lab (HF embed)" />
              <StatusPill ok={status.ready.proof_links} label="Proof links (Supabase)" />
            </div>

            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-4 space-y-2">
              <p className="font-medium">Hugging Face</p>
              {status.huggingface.configured ? (
                <p className="text-[var(--muted)]">
                  Token {status.huggingface.token_preview} · summarize:{' '}
                  {status.huggingface.summary_model} · embed: {status.huggingface.embed_model}
                </p>
              ) : (
                <p className="text-[var(--muted)]">HF_TOKEN not configured</p>
              )}
              {!status.huggingface.summarize.ok && status.huggingface.summarize.error && (
                <p className="text-[var(--danger)]">Summarize: {status.huggingface.summarize.error}</p>
              )}
              {!status.huggingface.embed.ok && status.huggingface.embed.error && (
                <p className="text-[var(--danger)]">Embed: {status.huggingface.embed.error}</p>
              )}
              {status.huggingface.embed.ok && status.huggingface.embed.dimensions && (
                <p className="text-emerald-400/90">
                  Embeddings OK ({status.huggingface.embed.dimensions} dimensions)
                </p>
              )}
            </div>

            <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-4 space-y-2">
              <p className="font-medium">Supabase</p>
              {status.supabase.configured ? (
                <p className="text-[var(--muted)]">Project {status.supabase.url_preview}</p>
              ) : (
                <p className="text-[var(--muted)]">Not configured (optional for proof URLs)</p>
              )}
              {status.supabase.error && (
                <p className={status.supabase.can_write ? 'text-[var(--muted)]' : 'text-[var(--danger)]'}>
                  {status.supabase.error}
                </p>
              )}
            </div>
          </div>
        )}
      </section>

      <section className="card space-y-5">
        <h2 className="font-semibold">Get your Hugging Face API token</h2>
        <ol className="space-y-4">
          {HF_STEPS.map((step, i) => (
            <li key={step.title} className="flex gap-4">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/20 text-xs font-bold text-[var(--accent)]">
                {i + 1}
              </span>
              <div>
                <p className="font-medium">{step.title}</p>
                <p className="mt-1 text-sm text-[var(--muted)] leading-relaxed">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
        <a
          href="https://huggingface.co/settings/tokens/new?tokenType=fineGrained"
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary inline-block text-sm"
        >
          Open Hugging Face token creator →
        </a>
      </section>

      <section className="card space-y-4">
        <h2 className="font-semibold">Add keys locally</h2>
        <p className="text-sm text-[var(--muted)]">
          Option A — interactive script (recommended on Windows):
        </p>
        <pre className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--bg)] p-4 text-xs">
          cd portfolio-mentor-platform{'\n'}
          .\scripts\setup-lab-env.ps1
        </pre>
        <p className="text-sm text-[var(--muted)]">
          Option B — copy{' '}
          <code className="rounded bg-[var(--bg)] px-1">.env.example</code> to{' '}
          <code className="rounded bg-[var(--bg)] px-1">.env.local</code> and paste your token:
        </p>
        <pre className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--bg)] p-4 text-xs whitespace-pre-wrap">
          {envBlock}
        </pre>
        <p className="text-sm text-[var(--muted)]">
          Restart <code className="rounded bg-[var(--bg)] px-1">npm run dev</code> after saving, then
          click Re-check above.
        </p>
      </section>

      <section className="card space-y-3">
        <h2 className="font-semibold">Production (Vercel)</h2>
        <p className="text-sm text-[var(--muted)] leading-relaxed">
          Vercel → your project → Settings → Environment Variables. Add the same{' '}
          <code className="rounded bg-[var(--bg)] px-1">HF_TOKEN</code>, model names, and Supabase
          keys. Set <code className="rounded bg-[var(--bg)] px-1">NEXT_PUBLIC_APP_URL</code> to your
          live Vercel URL so proof links resolve correctly. Redeploy after saving.
        </p>
        <Link href="/lab/rag" className="text-sm text-[var(--accent)] hover:underline">
          Try RAG lab →
        </Link>
      </section>
    </div>
  );
}
