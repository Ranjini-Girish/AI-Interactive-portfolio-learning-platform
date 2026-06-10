'use client';

import { useEffect, useState } from 'react';
import type { OverlayMessage } from '@/lib/interview/types';
import { OVERLAY_CHANNEL } from '@/lib/interview/types';
import './overlay.css';

type OverlayState = {
  question: string;
  answer: string;
  bullets: string[];
  listening: boolean;
};

export default function InterviewOverlayPage() {
  const [state, setState] = useState<OverlayState>({
    question: '',
    answer: 'Open Live session and click “Open private overlay”.',
    bullets: [],
    listening: false,
  });
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    document.documentElement.classList.add('overlay-root');
    return () => document.documentElement.classList.remove('overlay-root');
  }, []);

  useEffect(() => {
    const ch = new BroadcastChannel(OVERLAY_CHANNEL);
    ch.onmessage = (ev: MessageEvent<OverlayMessage>) => {
      const msg = ev.data;
      if (msg.type === 'state') {
        setState({
          question: msg.question,
          answer: msg.answer,
          bullets: msg.bullets,
          listening: msg.listening,
        });
      }
    };
    return () => ch.close();
  }, []);

  return (
    <div className={`overlay-shell ${compact ? 'overlay-compact' : ''}`}>
      <header className="overlay-bar">
        <span className={`overlay-dot ${state.listening ? 'overlay-dot-live' : ''}`} />
        <span className="overlay-title">Interview Copilot</span>
        <button type="button" className="overlay-btn" onClick={() => setCompact((c) => !c)}>
          {compact ? 'Expand' : 'Compact'}
        </button>
      </header>

      {state.question && (
        <section className="overlay-block">
          <p className="overlay-label">Question</p>
          <p className="overlay-question">{state.question}</p>
        </section>
      )}

      <section className="overlay-block overlay-answer-block">
        <p className="overlay-label">Say this</p>
        <p className="overlay-answer">{state.answer}</p>
      </section>

      {state.bullets.length > 0 && (
        <ul className="overlay-bullets">
          {state.bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}

      <footer className="overlay-footer">Only you see this window — do not share it.</footer>
    </div>
  );
}
