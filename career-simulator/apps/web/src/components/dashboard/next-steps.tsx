import Link from 'next/link';
import type { ProgressNextStep } from '@career-sim/shared';
import { ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const PRIORITY_STYLE: Record<ProgressNextStep['priority'], string> = {
  high: 'border-primary/30 bg-primary/5',
  medium: 'border-border',
  low: 'border-dashed border-border/80',
};

export function NextStepsCard({ steps }: { steps: ProgressNextStep[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Suggested next steps</CardTitle>
        <CardDescription>Personalized actions based on your progress and gaps</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {steps.map((step, i) => (
          <div
            key={step.id}
            className={`flex flex-col gap-2 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between ${PRIORITY_STYLE[step.priority]}`}
          >
            <div>
              <p className="text-xs text-muted-foreground">Step {i + 1}</p>
              <p className="font-medium">{step.title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
            </div>
            <Button asChild size="sm" variant={step.priority === 'high' ? 'default' : 'outline'}>
              <Link href={step.href}>
                Go <ArrowRight className="h-3 w-3" />
              </Link>
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
