'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import type { SimRole, SimTaskDefinition, SimTaskSubmitPayload } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { getAuthErrorMessage } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input, Label } from '@/components/ui/input';
import {
  fetchSimulationTaskFixtures,
  submitSimulationTask,
} from '@/lib/api-client';

type Defect = { id: string; label: string };
type ReviewSample = { id: string; prompt: string; response: string };
type DatasetRow = Record<string, string | number>;

function fieldClass(extra = '') {
  return `flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${extra}`;
}

function TaskWorkspace() {
  const params = useParams();
  const router = useRouter();
  const roleId = params.roleId as SimRole;
  const taskId = params.taskId as string;

  const [task, setTask] = useState<SimTaskDefinition | null>(null);
  const [fixtures, setFixtures] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [grade, setGrade] = useState<{ score: number; passed: boolean; feedback: string[] } | null>(
    null,
  );

  const [text, setText] = useState('');
  const [bug, setBug] = useState({ title: '', severity: 'High', steps: '', expected: '', actual: '' });
  const [order, setOrder] = useState<string[]>([]);
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [reviewFeedback, setReviewFeedback] = useState('');

  useEffect(() => {
    fetchSimulationTaskFixtures(roleId, taskId)
      .then((r) => {
        setTask(r.task);
        setFixtures(r.fixtures);
        const defects = (r.fixtures.defects as Defect[] | undefined) ?? [];
        if (defects.length) setOrder(defects.map((d) => d.id));
        const samples = (r.fixtures.samples as ReviewSample[] | undefined) ?? [];
        if (samples.length) {
          const init: Record<string, number> = {};
          samples.forEach((s) => {
            init[s.id] = 3;
          });
          setRatings(init);
        }
      })
      .catch((err) => setError(getAuthErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [roleId, taskId]);

  function moveDefect(index: number, dir: -1 | 1) {
    setOrder((prev) => {
      const next = [...prev];
      const target = index + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function buildPayload(): SimTaskSubmitPayload {
    if (!task) throw new Error('No task');
    switch (task.kind) {
      case 'test_cases':
        return { kind: 'test_cases', text };
      case 'bug_report':
        return { kind: 'bug_report', ...bug };
      case 'prioritize':
        return { kind: 'prioritize', order };
      case 'review':
        return { kind: 'review', ratings, feedback: reviewFeedback };
      default:
        return { kind: 'written', text };
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    setGrade(null);
    try {
      const result = await submitSimulationTask(roleId, taskId, buildPayload());
      setGrade(result.grade);
      if (result.grade.passed) {
        setTimeout(() => router.push(`/roles/${roleId}`), 1500);
      }
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <p className="p-10 text-center text-muted-foreground">Loading task…</p>;
  if (!task) return <p className="p-10 text-center text-destructive">{error || 'Task not found'}</p>;

  const defects = (fixtures.defects as Defect[] | undefined) ?? [];
  const dataset = (fixtures.dataset as DatasetRow[] | undefined) ?? [];
  const samples = (fixtures.samples as ReviewSample[] | undefined) ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href={`/roles/${roleId}`}>
          <ArrowLeft className="h-4 w-4" /> Back to module
        </Link>
      </Button>

      <header>
        <Badge className="mb-2">Work task</Badge>
        <h1 className="text-2xl font-bold">{task.title}</h1>
        <p className="mt-2 text-muted-foreground">{task.instruction}</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Scenario</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
            {task.scenario}
          </p>
        </CardContent>
      </Card>

      {dataset.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sample data</CardTitle>
            <CardDescription>Q1 sales — use these numbers in your insights</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b text-muted-foreground">
                  {Object.keys(dataset[0]).map((k) => (
                    <th key={k} className="px-2 py-1 font-medium capitalize">
                      {k}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataset.map((row, i) => (
                  <tr key={i} className="border-b border-border/50">
                    {Object.values(row).map((v, j) => (
                      <td key={j} className="px-2 py-1">
                        {typeof v === 'number' ? v.toLocaleString() : v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      <form onSubmit={onSubmit} className="space-y-4">
        {(task.kind === 'written' || task.kind === 'test_cases') && (
          <div className="space-y-2">
            <Label htmlFor="response">Your response</Label>
            <textarea
              id="response"
              className={fieldClass('min-h-[220px]')}
              placeholder={
                task.kind === 'test_cases'
                  ? 'Test Case 1: Valid login\nSteps:\n1) ...\nExpected: ...'
                  : 'Write your answer here…'
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              required
            />
          </div>
        )}

        {task.kind === 'bug_report' && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input id="title" value={bug.title} onChange={(e) => setBug({ ...bug, title: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="severity">Severity</Label>
              <select
                id="severity"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={bug.severity}
                onChange={(e) => setBug({ ...bug, severity: e.target.value })}
              >
                <option>Critical</option>
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="steps">Steps to reproduce</Label>
              <textarea id="steps" className={fieldClass()} value={bug.steps} onChange={(e) => setBug({ ...bug, steps: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="expected">Expected behavior</Label>
              <textarea id="expected" className={fieldClass('min-h-[80px]')} value={bug.expected} onChange={(e) => setBug({ ...bug, expected: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="actual">Actual behavior</Label>
              <textarea id="actual" className={fieldClass('min-h-[80px]')} value={bug.actual} onChange={(e) => setBug({ ...bug, actual: e.target.value })} required />
            </div>
          </div>
        )}

        {task.kind === 'prioritize' && (
          <div className="space-y-2">
            <Label>Priority order (most urgent first)</Label>
            <ul className="space-y-2">
              {order.map((id, i) => {
                const label = defects.find((d) => d.id === id)?.label ?? id;
                return (
                  <li key={id} className="flex items-center gap-2 rounded-lg border border-border p-3">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-muted text-xs font-medium">
                      {i + 1}
                    </span>
                    <span className="flex-1 text-sm">{label}</span>
                    <Button type="button" variant="ghost" size="icon" disabled={i === 0} onClick={() => moveDefect(i, -1)}>
                      <ChevronUp className="h-4 w-4" />
                    </Button>
                    <Button type="button" variant="ghost" size="icon" disabled={i === order.length - 1} onClick={() => moveDefect(i, 1)}>
                      <ChevronDown className="h-4 w-4" />
                    </Button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {task.kind === 'review' && (
          <div className="space-y-4">
            {samples.map((s) => (
              <Card key={s.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">User: {s.prompt}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="rounded-md bg-muted/50 p-3 text-sm">{s.response}</p>
                  <div className="flex items-center gap-3">
                    <Label htmlFor={`rate-${s.id}`}>Accuracy (1–5)</Label>
                    <Input
                      id={`rate-${s.id}`}
                      type="number"
                      min={1}
                      max={5}
                      className="w-20"
                      value={ratings[s.id] ?? 3}
                      onChange={(e) =>
                        setRatings({ ...ratings, [s.id]: parseInt(e.target.value, 10) || 3 })
                      }
                    />
                  </div>
                </CardContent>
              </Card>
            ))}
            <div className="space-y-2">
              <Label htmlFor="review-notes">Notes — flag any hallucinations</Label>
              <textarea id="review-notes" className={fieldClass()} value={reviewFeedback} onChange={(e) => setReviewFeedback(e.target.value)} required />
            </div>
          </div>
        )}

        {task.hints.length > 0 && (
          <Card className="border-dashed bg-muted/20">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Hints</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                {task.hints.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {grade && (
          <Card className={grade.passed ? 'border-primary/40 bg-primary/5' : 'border-destructive/30'}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                Score: {grade.score}% {grade.passed ? '— Passed' : '— Needs revision'}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1 text-sm">
                {grade.feedback.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
              {grade.passed && (
                <p className="mt-3 text-sm text-muted-foreground">Returning to module…</p>
              )}
            </CardContent>
          </Card>
        )}

        <Button type="submit" disabled={submitting}>
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Grading…
            </>
          ) : (
            'Submit for feedback'
          )}
        </Button>
      </form>
    </div>
  );
}

export default function TaskPage() {
  return (
    <AuthGuard>
      <TaskWorkspace />
    </AuthGuard>
  );
}
