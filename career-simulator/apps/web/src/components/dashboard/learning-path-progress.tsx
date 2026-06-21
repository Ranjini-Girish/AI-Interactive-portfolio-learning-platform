import type { ProgressLearningStep } from '@career-sim/shared';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function LearningPathProgress({ steps }: { steps: ProgressLearningStep[] }) {
  if (!steps.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Learning path</CardTitle>
          <CardDescription>Match a job description to unlock a step-by-step plan.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Learning path</CardTitle>
        <CardDescription>Track where you are in your personalized plan</CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="space-y-4">
          {steps.map((step) => {
            const icon =
              step.status === 'done' ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />
              ) : step.status === 'current' ? (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
              ) : (
                <Circle className="h-4 w-4 shrink-0 text-muted-foreground" />
              );

            return (
              <li key={step.step} className="flex gap-3">
                {icon}
                <div className={step.status === 'upcoming' ? 'opacity-60' : ''}>
                  <p className="text-sm font-medium">
                    Step {step.step}: {step.title}
                  </p>
                  <p className="text-xs text-muted-foreground">{step.description}</p>
                  <p className="mt-1 text-xs text-muted-foreground">~{step.estimatedDays} days</p>
                </div>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
