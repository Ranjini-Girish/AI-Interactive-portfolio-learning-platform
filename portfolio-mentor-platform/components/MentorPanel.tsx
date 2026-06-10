'use client';

import { useState } from 'react';
import type { Step } from '@/data/curriculum';
import type { MentorMessage } from '@/lib/progress';

type Props = {
  projectTitle: string;
  step: Step;
  messages: MentorMessage[];
  onSend: (userMessage: string, completedChecklist: string[]) => Promise<void>;
  completedChecklist: string[];
};

export function MentorPanel({
  projectTitle,
  step,
  messages,
  onSend,
  completedChecklist,
}: Props) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() && completedChecklist.length === 0) return;
    setLoading(true);
    try {
      await onSend(input.trim(), completedChecklist);
      setInput('');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card flex h-full min-h-[420px] flex-col">
      <div className="border-b border-[var(--border)] pb-3">
        <h3 className="font-semibold">AI Mentor</h3>
        <p className="mt-1 text-xs text-[var(--muted)]">
          Ask about blockers, architecture, or request feedback on your checklist. Wire an LLM
          API key in <code>.env.local</code> for live responses; works offline with rule-based
          feedback until then.
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto py-4">
        {messages.length === 0 && (
          <p className="text-sm text-[var(--muted)]">
            Start building <strong>{step.title}</strong>, then ask: &quot;I finished the API —
            does my response shape look right?&quot;
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`max-w-[95%] rounded-lg px-3 py-2 text-sm ${
              m.role === 'user'
                ? 'ml-auto bg-[var(--accent)] text-white'
                : 'bg-[var(--surface-2)] prose-mentor whitespace-pre-wrap'
            }`}
          >
            {m.content}
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-[var(--border)] pt-3">
        <textarea
          rows={3}
          placeholder={`Question about ${projectTitle} / ${step.title}…`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <div className="mt-2 flex justify-end">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Thinking…' : 'Get mentor feedback'}
          </button>
        </div>
      </form>
    </div>
  );
}
