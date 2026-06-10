'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import type { InterviewRound } from '@/lib/interview/types';
import {
  loadSession,
  loadUserApiKey,
  saveSession,
  saveUserApiKey,
} from '@/lib/interview/storage';

const ROUNDS: { id: InterviewRound; label: string; desc: string }[] = [
  { id: 'recruiter', label: 'Recruiter / HR', desc: 'Motivation, salary, culture, resume walkthrough' },
  { id: 'technical', label: 'Technical', desc: 'ML, system design, coding discussion, stack depth' },
  { id: 'behavioral', label: 'Behavioral', desc: 'STAR stories, leadership, conflict, teamwork' },
  { id: 'mixed', label: 'Mixed / unknown', desc: 'Auto-adapt to whatever is asked' },
];

export default function InterviewSetupPage() {
  const router = useRouter();
  const [jd, setJd] = useState('');
  const [resume, setResume] = useState('');
  const [round, setRound] = useState<InterviewRound>('mixed');
  const [company, setCompany] = useState('');
  const [roleTitle, setRoleTitle] = useState('');
  const [apiKey, setApiKey] = useState('');

  useEffect(() => {
    const s = loadSession();
    setJd(s.jobDescription);
    setResume(s.resume);
    setRound(s.round);
    setCompany(s.company ?? '');
    setRoleTitle(s.roleTitle ?? '');
    setApiKey(loadUserApiKey());
  }, []);

  function startLive() {
    if (!jd.trim() || !resume.trim()) {
      alert('Please paste the job description and your resume.');
      return;
    }
    saveSession({
      jobDescription: jd.trim(),
      resume: resume.trim(),
      round,
      company: company.trim(),
      roleTitle: roleTitle.trim(),
    });
    saveUserApiKey(apiKey.trim());
    router.push('/interview/live');
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10 sm:px-6">
      <header>
        <p className="text-sm font-medium text-[var(--accent)]">No signup · data stays in your browser</p>
        <h1 className="mt-2 text-3xl font-bold">Live Interview Copilot</h1>
        <p className="mt-3 text-[var(--muted)] leading-relaxed">
          Paste a job description and your resume. During the call, open the{' '}
          <strong className="text-[var(--text)]">private overlay</strong> on a second monitor or your phone —
          not the window you share in Zoom/Teams.
        </p>
      </header>

      <div className="card border-[var(--warning)]/40 bg-[color-mix(in_srgb,var(--warning)_8%,var(--surface))] text-sm">
        <strong className="text-[var(--warning)]">Keep it off the shared screen</strong>
        <ol className="mt-2 list-inside list-decimal space-y-1 text-[var(--muted)]">
          <li>In Zoom/Teams, share <strong className="text-[var(--text)]">Meeting tab only</strong> — not entire screen.</li>
          <li>Open the overlay on another monitor, phone, or separate window you do not share.</li>
          <li>Use headphones so mic picks up the interviewer, not your speakers.</li>
        </ol>
        <p className="mt-2 text-xs text-[var(--muted)]">
          Browsers cannot guarantee invisibility on full-screen share. The second-screen workflow is the reliable
          approach.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm">
          Company (optional)
          <input
            className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="e.g. Acme Bank"
          />
        </label>
        <label className="text-sm">
          Role title (optional)
          <input
            className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            value={roleTitle}
            onChange={(e) => setRoleTitle(e.target.value)}
            placeholder="e.g. Senior ML Engineer"
          />
        </label>
      </div>

      <fieldset className="card space-y-3">
        <legend className="text-sm font-semibold">Interview round</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {ROUNDS.map((r) => (
            <label
              key={r.id}
              className={`cursor-pointer rounded-lg border p-3 text-sm ${
                round === r.id
                  ? 'border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_12%,transparent)]'
                  : 'border-[var(--border)]'
              }`}
            >
              <input
                type="radio"
                name="round"
                className="sr-only"
                checked={round === r.id}
                onChange={() => setRound(r.id)}
              />
              <span className="font-medium">{r.label}</span>
              <p className="mt-1 text-xs text-[var(--muted)]">{r.desc}</p>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="block text-sm">
        Job description
        <textarea
          rows={8}
          className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 font-mono text-xs"
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          placeholder="Paste the full JD here…"
        />
      </label>

      <label className="block text-sm">
        Your resume
        <textarea
          rows={10}
          className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 font-mono text-xs"
          value={resume}
          onChange={(e) => setResume(e.target.value)}
          placeholder="Paste resume text here…"
        />
      </label>

      <label className="block text-sm">
        OpenAI API key (optional — better answers; stored only in your browser)
        <input
          type="password"
          className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 font-mono text-xs"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-… (leave blank to use free local coach)"
        />
      </label>

      <div className="flex flex-wrap gap-3">
        <button type="button" className="btn-primary" onClick={startLive}>
          Start live session
        </button>
        <Link href="/" className="btn-ghost">
          Back to portfolio
        </Link>
      </div>
    </div>
  );
}
