'use client';

import { useState } from 'react';
import Link from 'next/link';

const SAMPLE_DOCS = [
  {
    id: 'deductible',
    text: 'Standard homeowners policy: deductible is $1,000 per claim unless waived for catastrophe wind damage in coastal zones.',
  },
  {
    id: 'water',
    text: 'Water backup from sewers or drains is excluded unless the Water Backup Endorsement is purchased before loss.',
  },
  {
    id: 'jewelry',
    text: 'Scheduled personal property covers jewelry up to $5,000 per item; unscheduled jewelry sublimit is $1,500.',
  },
  {
    id: 'rental',
    text: 'Loss of use provides additional living expenses for up to 12 months when the residence is uninhabitable after a covered loss.',
  },
  {
    id: 'flood',
    text: 'Flood damage is not covered under the homeowners form; NFIP or private flood policy required.',
  },
];

type RagHit = { id: string; text: string; score: number };

export default function RagLabPage() {
  const [query, setQuery] = useState('Is sewer backup covered?');
  const [hits, setHits] = useState<RagHit[]>([]);
  const [meta, setMeta] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function runSearch() {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/inference/rag/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          documents: SAMPLE_DOCS,
          top_k: 3,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? 'Search failed');
      }
      const data = await res.json();
      setHits(data.hits ?? []);
      setMeta(
        data.model
          ? `Embeddings: ${data.provider} · ${data.model}`
          : `${data.provider} embedding fallback (set HF_TOKEN for semantic search)`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed');
      setHits([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10 sm:px-6">
      <header>
        <p className="text-sm font-medium text-[var(--accent)]">Lab 3 · Policy Document RAG</p>
        <h1 className="mt-2 text-3xl font-bold">Semantic search over policy snippets</h1>
        <p className="mt-3 text-[var(--muted)] leading-relaxed">
          This lab calls the same inference stack used in production RAG: embed the question and
          policy chunks with Hugging Face (or a local fallback), then rank by cosine similarity.
        </p>
        <p className="mt-2 text-sm">
          <Link href="/lab/setup" className="text-[var(--accent)] hover:underline">
            Set up Hugging Face API keys →
          </Link>
        </p>
      </header>

      <section className="card space-y-4">
        <label className="block text-sm">
          Ask a policy question
          <input
            className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button type="button" className="btn-primary" disabled={loading} onClick={runSearch}>
          {loading ? 'Searching…' : 'Retrieve relevant clauses'}
        </button>
        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
        {meta && <p className="text-xs text-[var(--muted)]">{meta}</p>}
      </section>

      {hits.length > 0 && (
        <section className="card space-y-3">
          <h2 className="font-semibold">Top matches</h2>
          {hits.map((h) => (
            <article
              key={h.id}
              className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3 text-sm"
            >
              <p className="text-xs font-semibold text-[var(--accent)]">
                {h.id} · score {h.score.toFixed(3)}
              </p>
              <p className="mt-2 text-[var(--muted)]">{h.text}</p>
            </article>
          ))}
        </section>
      )}

      <p className="text-sm text-[var(--muted)]">
        Next step in Build Lab:{' '}
        <Link href="/build/projects/policy-document-rag" className="text-[var(--accent)] hover:underline">
          Policy Document RAG learning path
        </Link>
      </p>
    </div>
  );
}
