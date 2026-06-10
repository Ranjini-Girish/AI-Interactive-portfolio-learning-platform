'use client';

import { useCallback, useState } from 'react';
import type { InterviewSession, SuggestResponse } from '@/lib/interview/types';
import { loadUserApiKey } from '@/lib/interview/storage';

export function useInterviewCoach(session: InterviewSession) {
  const [loading, setLoading] = useState(false);
  const [lastQuestion, setLastQuestion] = useState('');
  const [suggestion, setSuggestion] = useState<SuggestResponse | null>(null);
  const [error, setError] = useState('');

  const fetchSuggestion = useCallback(
    async (question: string, transcriptTail?: string) => {
      const q = question.trim();
      if (!q) return;
      setLoading(true);
      setError('');
      setLastQuestion(q);

      try {
        const res = await fetch('/api/interview/suggest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session,
            question: q,
            transcriptTail,
            userApiKey: loadUserApiKey() || undefined,
          }),
        });
        if (!res.ok) throw new Error('Could not generate suggestion');
        const data = (await res.json()) as SuggestResponse;
        setSuggestion(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed');
      } finally {
        setLoading(false);
      }
    },
    [session],
  );

  return { loading, lastQuestion, suggestion, error, fetchSuggestion, setSuggestion };
}

/** Heuristic: interviewer finished asking something. */
export function looksLikeQuestion(text: string): boolean {
  const t = text.trim();
  if (t.length < 12) return false;
  if (t.endsWith('?')) return true;
  return /^(tell me|describe|explain|why|how|what|when|where|walk me|give me|can you|could you|have you|do you)/i.test(
    t,
  );
}
