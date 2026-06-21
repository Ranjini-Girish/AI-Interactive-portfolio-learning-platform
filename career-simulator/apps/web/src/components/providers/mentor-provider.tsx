'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { MentorMessage, MentorStatusResponse } from '@career-sim/shared';
import { MENTOR_STARTER_PROMPTS } from '@career-sim/shared';
import { fetchMentorHistory, fetchMentorStatus, clearMentorHistory } from '@/lib/api-client';
import { streamMentorChat } from '@/lib/mentor-stream';
import { useAuth } from '@/components/providers/auth-provider';

type MentorContextValue = {
  messages: MentorMessage[];
  loading: boolean;
  streaming: boolean;
  status: MentorStatusResponse | null;
  starterPrompts: string[];
  sendMessage: (text: string) => Promise<void>;
  clearChat: () => Promise<void>;
};

const MentorContext = createContext<MentorContextValue | null>(null);

export function MentorProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<MentorMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<MentorStatusResponse | null>(null);

  useEffect(() => {
    if (!user) {
      setMessages([]);
      setStatus(null);
      return;
    }
    fetchMentorStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
    fetchMentorHistory()
      .then((r) => setMessages(r.messages))
      .catch(() => setMessages([]));
  }, [user]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming || !user) return;

      setStreaming(true);
      const userMsg: MentorMessage = { role: 'user', content: trimmed };
      setMessages((prev) => [...prev, userMsg]);

      let assistant = '';
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      await streamMentorChat(trimmed, {
        onToken: (chunk) => {
          assistant += chunk;
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = { role: 'assistant', content: assistant };
            return copy;
          });
        },
        onError: (err) => {
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = {
              role: 'assistant',
              content: `Sorry — ${err}. Add OPENAI_API_KEY to .env for live AI, or try a starter prompt.`,
            };
            return copy;
          });
        },
        onDone: () => setStreaming(false),
      });

      setStreaming(false);
    },
    [streaming, user],
  );

  const clearChat = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      await clearMentorHistory();
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }, [user]);

  const value = useMemo(
    () => ({
      messages,
      loading,
      streaming,
      status,
      starterPrompts: [...MENTOR_STARTER_PROMPTS],
      sendMessage,
      clearChat,
    }),
    [messages, loading, streaming, status, sendMessage, clearChat],
  );

  return <MentorContext.Provider value={value}>{children}</MentorContext.Provider>;
}

export function useMentor() {
  const ctx = useContext(MentorContext);
  if (!ctx) throw new Error('useMentor must be used within MentorProvider');
  return ctx;
}

/** Safe hook for layout — returns null when outside provider or logged out */
export function useMentorOptional() {
  return useContext(MentorContext);
}
