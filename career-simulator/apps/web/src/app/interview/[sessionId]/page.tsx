'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, Loader2 } from 'lucide-react';
import type { InterviewAnswerFeedback, InterviewSessionRecord } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { InterviewFeedbackPanel } from '@/components/interview/feedback-panel';
import { InterviewResults } from '@/components/interview/session-results';
import { getAuthErrorMessage } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchInterviewSession, submitInterviewAnswer } from '@/lib/api-client';

function SessionContent() {
  const params = useParams();
  const sessionId = params.sessionId as string;

  const [session, setSession] = useState<InterviewSessionRecord | null>(null);
  const [answer, setAnswer] = useState('');
  const [feedback, setFeedback] = useState<InterviewAnswerFeedback | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchInterviewSession(sessionId)
      .then((r) => setSession(r.session))
      .catch(() => setError('Session not found'))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const currentQuestion = session?.pendingQuestions[0] ?? null;
  const progress = session
    ? Math.round((session.questionsAnswered / session.questionsTotal) * 100)
    : 0;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!currentQuestion) return;
    setError('');
    setSubmitting(true);
    setFeedback(null);
    try {
      const result = await submitInterviewAnswer(sessionId, currentQuestion.id, answer);
      setFeedback(result.feedback);
      setSession(result.session);
      setAnswer('');
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  function nextQuestion() {
    setFeedback(null);
  }

  if (loading) return <p className="p-10 text-center text-muted-foreground">Loading interview…</p>;
  if (!session) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <p className="text-destructive">{error || 'Session not found'}</p>
        <Button asChild className="mt-4" variant="outline">
          <Link href="/interview">Back</Link>
        </Button>
      </div>
    );
  }

  if (session.status === 'completed' && !feedback) {
    return (
      <div className="mx-auto max-w-2xl space-y-6 px-4 py-10">
        <Button asChild variant="ghost" size="sm">
          <Link href="/interview">
            <ArrowLeft className="h-4 w-4" /> All interviews
          </Link>
        </Button>
        <InterviewResults session={session} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-10">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href="/interview">
          <ArrowLeft className="h-4 w-4" /> Exit
        </Link>
      </Button>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          Question {session.questionsAnswered + 1} of {session.questionsTotal}
        </span>
        <Badge variant="outline">{currentQuestion?.type ?? '…'}</Badge>
      </div>

      {currentQuestion && !feedback && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base leading-relaxed">{currentQuestion.text}</CardTitle>
            <CardDescription>Tip: {currentQuestion.tip}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              <textarea
                className="flex min-h-[200px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                placeholder="Type your answer as if speaking to an interviewer…"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                required
                minLength={30}
              />
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" disabled={submitting || answer.trim().length < 30}>
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Grading…
                  </>
                ) : (
                  'Submit answer'
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {feedback && (
        <div className="space-y-4">
          <InterviewFeedbackPanel feedback={feedback} />
          {session.status === 'completed' ? (
            <InterviewResults session={session} />
          ) : session.pendingQuestions.length > 0 ? (
            <Button onClick={nextQuestion}>Next question</Button>
          ) : null}
        </div>
      )}

      <p className="text-xs text-muted-foreground">Progress: {progress}%</p>
    </div>
  );
}

export default function InterviewSessionPage() {
  return (
    <AuthGuard>
      <SessionContent />
    </AuthGuard>
  );
}
