'use client';

import type { InterviewAnswerFeedback } from '@career-sim/shared';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

export function InterviewFeedbackPanel({ feedback }: { feedback: InterviewAnswerFeedback }) {
  return (
    <Card className={feedback.passed ? 'border-primary/40 bg-primary/5' : 'border-amber-500/30'}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Feedback</CardTitle>
          <Badge variant={feedback.passed ? 'default' : 'outline'}>{feedback.score}%</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <Progress value={feedback.score} className="h-2" />
        <div>
          <p className="font-medium text-primary">Strengths</p>
          <ul className="mt-1 list-inside list-disc text-muted-foreground">
            {feedback.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-medium">Improve</p>
          <ul className="mt-1 list-inside list-disc text-muted-foreground">
            {feedback.improvements.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-md bg-muted/50 p-3">
          <p className="text-xs font-medium">Sample structure</p>
          <p className="mt-1 text-xs text-muted-foreground">{feedback.sampleOutline}</p>
        </div>
        <Badge variant="secondary" className="text-xs">
          {feedback.provider === 'openai' ? 'AI coach' : 'Local coach'}
        </Badge>
      </CardContent>
    </Card>
  );
}
