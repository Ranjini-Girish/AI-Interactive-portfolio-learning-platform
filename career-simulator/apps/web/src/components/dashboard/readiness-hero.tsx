import type { ProgressDashboard } from '@career-sim/shared';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

const LABEL_COLORS: Record<ProgressDashboard['readiness']['label'], string> = {
  'Getting started': 'bg-muted text-muted-foreground',
  'Building skills': 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  'Interview ready': 'bg-primary/15 text-primary',
  'Job ready': 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
};

export function ReadinessHero({ readiness }: { readiness: ProgressDashboard['readiness'] }) {
  return (
    <Card className="border-primary/20 bg-gradient-to-br from-primary/10 via-background to-background">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-lg">Job readiness</CardTitle>
          <Badge className={LABEL_COLORS[readiness.label]}>{readiness.label}</Badge>
        </div>
        <CardDescription>Weighted score from resume, job match, and simulation practice</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-3">
          <span className="text-5xl font-bold tabular-nums">{readiness.score}</span>
          <span className="mb-2 text-2xl text-muted-foreground">/ 100</span>
        </div>
        <Progress value={readiness.score} className="h-3" />
        <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
          <div className="rounded-md border border-border/60 px-3 py-2">
            <p className="font-medium text-foreground">Resume match</p>
            <p>{readiness.breakdown.resumeMatch ?? '—'}%</p>
          </div>
          <div className="rounded-md border border-border/60 px-3 py-2">
            <p className="font-medium text-foreground">Job match</p>
            <p>{readiness.breakdown.jobMatch ?? '—'}%</p>
          </div>
          <div className="rounded-md border border-border/60 px-3 py-2">
            <p className="font-medium text-foreground">Simulation</p>
            <p>{readiness.breakdown.simulationProgress}%</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
