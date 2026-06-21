'use client';

import Link from 'next/link';
import type { InterviewSessionRecord } from '@career-sim/shared';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

export function InterviewResults({ session }: { session: InterviewSessionRecord }) {
  const score = session.overallScore ?? 0;

  return (
    <div className="space-y-6">
      <Card className="border-primary/20 bg-primary/5">
        <CardHeader>
          <CardTitle className="text-lg">Interview complete</CardTitle>
          <CardDescription>
            {session.questionsAnswered} questions · Overall score
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-4xl font-bold tabular-nums">{score}%</p>
          <Progress value={score} className="mt-3" />
          <p className="mt-2 text-sm text-muted-foreground">
            {score >= 80
              ? 'Excellent — you are interview-ready on these topics.'
              : score >= 65
                ? 'Good job — refine structure and add specific examples.'
                : 'Keep practicing — use STAR for behavioral and numbered steps for technical.'}
          </p>
        </CardContent>
      </Card>

      {session.improvementSummary.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Improvement plan</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-2 text-sm text-muted-foreground">
              {session.improvementSummary.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link href="/interview">Start another interview</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
      </div>
    </div>
  );
}
