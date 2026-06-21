import Link from 'next/link';
import type { ProgressModuleSummary } from '@career-sim/shared';
import { CheckCircle2, Circle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

export function ModulesGrid({ modules }: { modules: ProgressModuleSummary[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Simulation modules</CardTitle>
        <CardDescription>Real company-style practice across four roles</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {modules.map((mod) => (
          <div key={mod.roleId} className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {mod.status === 'completed' ? (
                  <CheckCircle2 className="h-4 w-4 text-primary" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground" />
                )}
                <span className="text-sm font-medium">{mod.label}</span>
              </div>
              <span className="text-xs text-muted-foreground">
                {mod.tasksCompleted}/{mod.totalTasks}
              </span>
            </div>
            <Progress value={mod.progressPercent} className="h-2" />
            {mod.status !== 'completed' && (
              <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs">
                <Link href={`/roles/${mod.roleId}`}>
                  {mod.status === 'not_started' ? 'Start' : 'Continue'}
                </Link>
              </Button>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
