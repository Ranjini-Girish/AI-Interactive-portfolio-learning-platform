'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { looksLikeQuestion, useInterviewCoach } from '@/lib/interview/use-coach';
import { useInterviewListener } from '@/lib/interview/use-speech';
import { loadSession } from '@/lib/interview/storage';
import type { InterviewSession, OverlayMessage } from '@/lib/interview/types';
import { OVERLAY_CHANNEL } from '@/lib/interview/types';

function broadcast(msg: OverlayMessage) {
  try {
    const ch = new BroadcastChannel(OVERLAY_CHANNEL);
    ch.postMessage(msg);
    ch.close();
  } catch {
    /* ignore */
  }
}

export default function LiveInterviewPage() {
  const router = useRouter();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [manualQ, setManualQ] = useState('');
  const [transcript, setTranscript] = useState<string[]>([]);
  const [autoDetect, setAutoDetect] = useState(true);
  const overlayRef = useRef<Window | null>(null);
  const lastAutoRef = useRef('');

  useEffect(() => {
    const s = loadSession();
    if (!s.jobDescription.trim() || !s.resume.trim()) {
      router.replace('/interview');
      return;
    }
    setSession(s);
  }, [router]);

  const { loading, lastQuestion, suggestion, error, fetchSuggestion } = useInterviewCoach(
    session ?? { jobDescription: '', resume: '', round: 'mixed' },
  );

  const onSpeechFinal = useCallback(
    (text: string) => {
      setTranscript((prev) => [...prev.slice(-12), text]);
      if (autoDetect && looksLikeQuestion(text) && text !== lastAutoRef.current) {
        lastAutoRef.current = text;
        const tail = [...transcript, text].join(' ');
        void fetchSuggestion(text, tail);
      }
    },
    [autoDetect, fetchSuggestion, transcript],
  );

  const { listening, interim, supported, start, stop } = useInterviewListener(
    Boolean(session),
    onSpeechFinal,
  );

  useEffect(() => {
    if (!suggestion) return;
    broadcast({
      type: 'state',
      question: lastQuestion,
      answer: suggestion.answer,
      bullets: suggestion.bullets,
      listening,
    });
  }, [suggestion, lastQuestion, listening]);

  useEffect(() => {
    broadcast({
      type: 'state',
      question: lastQuestion,
      answer: suggestion?.answer ?? 'Waiting for a question…',
      bullets: suggestion?.bullets ?? [],
      listening,
    });
  }, [listening, lastQuestion, suggestion]);

  function openOverlay() {
    const w = window.open(
      '/interview/overlay',
      'interview-overlay',
      'width=420,height=640,alwaysOnTop=yes,menubar=no,toolbar=no,location=no,status=no',
    );
    overlayRef.current = w;
    if (w) {
      setTimeout(() => broadcast({ type: 'ping' }), 500);
    }
  }

  function submitManual() {
    const q = manualQ.trim();
    if (!q) return;
    void fetchSuggestion(q, transcript.join(' '));
    setManualQ('');
  }

  if (!session) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-[var(--muted)]">
        Loading session…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Live session</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {session.round} · {session.company || 'Interview'} · {session.roleTitle || 'Role'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-primary" onClick={openOverlay}>
            Open private overlay
          </button>
          <Link href="/interview" className="btn-ghost">
            Edit JD / resume
          </Link>
        </div>
      </header>

      <div className="card border-[var(--accent)]/30 text-sm">
        <strong>Before you join the call:</strong> open the overlay on your phone or second monitor. In Zoom/Teams,
        share <em>this meeting tab only</em> — not your whole screen.
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card space-y-4">
          <h2 className="font-semibold">Listen (mic)</h2>
          {!supported && (
            <p className="text-sm text-[var(--warning)]">
              Speech recognition is not supported in this browser. Type questions manually below.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={listening ? 'btn-ghost border-[var(--danger)] text-[var(--danger)]' : 'btn-primary'}
              onClick={listening ? stop : start}
              disabled={!supported}
            >
              {listening ? 'Stop listening' : 'Start listening'}
            </button>
            <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
              <input
                type="checkbox"
                checked={autoDetect}
                onChange={(e) => setAutoDetect(e.target.checked)}
              />
              Auto-detect questions
            </label>
          </div>
          {interim && (
            <p className="rounded-lg bg-[var(--bg)] p-2 text-xs text-[var(--muted)]">
              Hearing: {interim}
            </p>
          )}
          {transcript.length > 0 && (
            <div className="max-h-32 overflow-y-auto text-xs text-[var(--muted)]">
              {transcript.slice(-6).map((t, i) => (
                <p key={i}>{t}</p>
              ))}
            </div>
          )}
        </section>

        <section className="card space-y-3">
          <h2 className="font-semibold">Type a question</h2>
          <textarea
            rows={3}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm"
            value={manualQ}
            onChange={(e) => setManualQ(e.target.value)}
            placeholder="Paste or type what the interviewer asked…"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submitManual();
            }}
          />
          <button type="button" className="btn-primary" onClick={submitManual} disabled={loading}>
            Get answer
          </button>
        </section>
      </div>

      <section className="card space-y-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-semibold">Coach panel</h2>
          {suggestion && (
            <span className="badge text-xs">
              {suggestion.source === 'openai' ? 'AI' : 'Local coach'}
            </span>
          )}
        </div>

        {loading && <p className="text-sm text-[var(--muted)]">Generating answer…</p>}
        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}

        {lastQuestion && (
          <div>
            <p className="text-xs uppercase tracking-wide text-[var(--muted)]">Question</p>
            <p className="mt-1 text-sm">{lastQuestion}</p>
          </div>
        )}

        {suggestion && (
          <>
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--muted)]">Suggested answer</p>
              <p className="mt-2 whitespace-pre-wrap leading-relaxed">{suggestion.answer}</p>
            </div>
            {suggestion.bullets.length > 0 && (
              <ul className="list-inside list-disc space-y-1 text-sm text-[var(--muted)]">
                {suggestion.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
            {suggestion.followUpTip && (
              <p className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3 text-sm">
                <strong>Follow-up tip:</strong> {suggestion.followUpTip}
              </p>
            )}
          </>
        )}

        {!suggestion && !loading && (
          <p className="text-sm text-[var(--muted)]">
            Start listening or type a question. Answers appear here and on the overlay window.
          </p>
        )}
      </section>
    </div>
  );
}
