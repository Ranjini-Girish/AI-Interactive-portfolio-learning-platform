'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Mic, Loader2 } from 'lucide-react';
import type { InterviewMode, InterviewSessionSummary, SimRole } from '@career-sim/shared';
import { SIM_ROLES } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { getAuthErrorMessage } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchInterviewSessions, fetchInterviewStatus, startInterviewSession } from '@/lib/api-client';

const MODES: { id: InterviewMode; label: string; desc: string }[] = [
  { id: 'behavioral', label: 'Behavioral', desc: '4 STAR-style questions' },
  { id: 'technical', label: 'Technical', desc: '4 role-specific questions' },
  { id: 'mixed', label: 'Mixed', desc: '3 behavioral + 3 technical' },
];

function InterviewHome() {
  const router = useRouter();
  const [roleId, setRoleId] = useState<SimRole>('qa_tester');
  const [mode, setMode] = useState<InterviewMode>('mixed');
  const [sessions, setSessions] = useState<InterviewSessionSummary[]>([]);
  const [aiConfigured, setAiConfigured] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchInterviewStatus()
      .then((s) => setAiConfigured(s.configured))
      .catch(() => {});
    fetchInterviewSessions()
      .then((r) => setSessions(r.sessions))
      .catch(() => {});
  }, []);

  async function handleStart() {
    setError('');
    setStarting(true);
    try {
      const { session } = await startInterviewSession(roleId, mode);
      router.push(`/interview/${session.id}`);
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header>
        <Badge className="mb-2">Phase 9 — Mock interviews</Badge>
        <h1 className="text-2xl font-bold">Mock interview practice</h1>
        <p className="mt-2 text-muted-foreground">
          Behavioral and technical questions with instant feedback, scoring, and improvement tips.
          {aiConfigured ? ' Powered by OpenAI.' : ' Local coach mode (add OPENAI_API_KEY for AI feedback).'}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Target role</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {SIM_ROLES.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setRoleId(r.id)}
              className={`rounded-lg border px-3 py-2 text-sm ${
                roleId === r.id ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted'
              }`}
            >
              {r.label}
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Interview type</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMode(m.id)}
              className={`rounded-lg border p-4 text-left ${
                mode === m.id ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted'
              }`}
            >
              <p className="font-medium">{m.label}</p>
              <p className="mt-1 text-xs text-muted-foreground">{m.desc}</p>
            </button>
          ))}
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Button size="lg" onClick={handleStart} disabled={starting}>
        {starting ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Starting…
          </>
        ) : (
          <>
            <Mic className="h-4 w-4" /> Start mock interview
          </>
        )}
      </Button>

      {sessions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent interviews</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {sessions.slice(0, 5).map((s) => (
              <Link
                key={s.id}
                href={`/interview/${s.id}`}
                className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted"
              >
                <span>
                  {SIM_ROLES.find((r) => r.id === s.roleId)?.label} · {s.interviewType}
                </span>
                <span className="text-muted-foreground">
                  {s.status === 'completed' ? `${s.overallScore}%` : 'In progress'}
                </span>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function InterviewPage() {
  return (
    <AuthGuard>
      <InterviewHome />
    </AuthGuard>
  );
}
