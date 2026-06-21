'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { Bot, Loader2, Trash2 } from 'lucide-react';
import { useMentorOptional } from '@/components/providers/mentor-provider';
import { useAuth } from '@/components/providers/auth-provider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

function MentorChatPanel({ className = '' }: { className?: string }) {
  const mentor = useMentorOptional();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [mentor?.messages, mentor?.streaming]);

  if (!mentor) return null;

  const { sendMessage, clearChat, streaming, messages, status, starterPrompts } = mentor;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input;
    setInput('');
    await sendMessage(text);
  }

  return (
    <div className={`flex flex-col ${className}`}>
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-primary" />
          <div>
            <p className="text-sm font-semibold">AI Work Mentor</p>
            <p className="text-xs text-muted-foreground">
              {status?.configured ? status.model : 'Local guide mode'}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          title="Clear chat"
          disabled={streaming || messages.length === 0}
          onClick={() => clearChat()}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Ask anything — I explain in plain English with examples, like a senior colleague.
            </p>
            {starterPrompts.map((p) => (
              <button
                key={p}
                type="button"
                className="block w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-left text-xs hover:bg-muted"
                onClick={() => sendMessage(p)}
              >
                {p}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-lg px-3 py-2 text-sm ${
              m.role === 'user'
                ? 'ml-6 bg-primary text-primary-foreground'
                : 'mr-4 bg-muted/60 text-foreground'
            }`}
          >
            <p className="whitespace-pre-wrap leading-relaxed">{m.content || '…'}</p>
          </div>
        ))}
        {streaming && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Mentor is typing…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="border-t border-border p-3">
        <div className="flex gap-2">
          <Input
            placeholder="Ask your mentor…"
            value={input}
            disabled={streaming}
            onChange={(e) => setInput(e.target.value)}
          />
          <Button type="submit" disabled={streaming || !input.trim()}>
            Send
          </Button>
        </div>
      </form>
    </div>
  );
}

export function MentorSidebar() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <aside className="hidden h-[calc(100vh-3.5rem)] w-80 shrink-0 border-l border-border bg-card/50 lg:flex lg:flex-col">
      <MentorChatPanel className="h-full" />
    </aside>
  );
}

export function MentorMobileFab() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);

  if (!user) return null;

  return (
    <>
      <button
        type="button"
        className="fixed bottom-4 right-4 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg lg:hidden"
        onClick={() => setOpen(true)}
        aria-label="Open AI mentor"
      >
        <Bot className="h-6 w-6" />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="absolute bottom-0 left-0 right-0 flex max-h-[85vh] flex-col rounded-t-xl bg-background shadow-xl">
            <div className="flex justify-center py-2">
              <div className="h-1 w-10 rounded-full bg-muted" />
            </div>
            <MentorChatPanel className="min-h-[60vh] flex-1" />
            <Button variant="ghost" className="m-2" onClick={() => setOpen(false)}>
              Close
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
