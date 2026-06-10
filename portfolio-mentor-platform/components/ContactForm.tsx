'use client';

import { useState } from 'react';

type FormState = {
  name: string;
  email: string;
  subject: string;
  message: string;
};

const initial: FormState = {
  name: '',
  email: '',
  subject: '',
  message: '',
};

export function ContactForm() {
  const [form, setForm] = useState<FormState>(initial);
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [feedback, setFeedback] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus('loading');
    setFeedback('');

    try {
      const res = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Failed to send');
      setStatus('success');
      if (data.channel === 'mailto' && data.mailto) {
        setFeedback(`${data.message} Opening your email client…`);
        window.location.href = data.mailto;
      } else {
        setFeedback(data.message ?? 'Message sent.');
      }
      setForm(initial);
    } catch (err) {
      setStatus('error');
      setFeedback(err instanceof Error ? err.message : 'Something went wrong.');
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card space-y-4">
      <div>
        <label htmlFor="name">Name</label>
        <input
          id="name"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
      </div>
      <div>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          required
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
      </div>
      <div>
        <label htmlFor="subject">Subject</label>
        <input
          id="subject"
          required
          value={form.subject}
          onChange={(e) => setForm({ ...form, subject: e.target.value })}
        />
      </div>
      <div>
        <label htmlFor="message">Message</label>
        <textarea
          id="message"
          required
          rows={5}
          value={form.message}
          onChange={(e) => setForm({ ...form, message: e.target.value })}
        />
      </div>
      <button type="submit" className="btn-primary w-full sm:w-auto" disabled={status === 'loading'}>
        {status === 'loading' ? 'Sending…' : 'Send message'}
      </button>
      {feedback && (
        <p className={status === 'success' ? 'text-[var(--success)] text-sm' : 'error'}>{feedback}</p>
      )}
    </form>
  );
}
