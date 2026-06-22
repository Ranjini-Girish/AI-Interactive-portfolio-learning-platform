import { API_URL } from './api-client';
import { getAuthToken } from './auth-token';

export type StreamCallbacks = {
  onToken: (text: string) => void;
  onMeta?: (meta: { provider?: string; model?: string }) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
};

export async function streamMentorChat(
  message: string,
  callbacks: StreamCallbacks,
  options?: { clearHistory?: boolean },
): Promise<void> {
  const token = await getAuthToken();
  if (!token) {
    callbacks.onError?.('Sign in to chat with your mentor');
    return;
  }

  const res = await fetch(`${API_URL}/api/mentor/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, clearHistory: options?.clearHistory }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    callbacks.onError?.(err.error ?? 'Mentor request failed');
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError?.('Streaming not supported');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;

      try {
        const data = JSON.parse(raw) as {
          content?: string;
          error?: string;
          done?: boolean;
          provider?: string;
          model?: string;
        };

        if (data.error) callbacks.onError?.(data.error);
        if (data.provider) callbacks.onMeta?.({ provider: data.provider, model: data.model });
        if (data.content) callbacks.onToken(data.content);
        if (data.done) callbacks.onDone?.();
      } catch {
        // ignore malformed chunks
      }
    }
  }

  callbacks.onDone?.();
}
