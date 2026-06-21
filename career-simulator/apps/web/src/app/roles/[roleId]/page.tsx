'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, CheckCircle2, Circle, Lock } from 'lucide-react';
import type { SimModuleDetail, SimRole, SimulationSessionRecord } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { getAuthErrorMessage } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  fetchSimulationModule,
  fetchSimulationSession,
  startSimulationSession,
} from '@/lib/api-client';

function ModuleContent() {
  const params = useParams();
  const roleId = params.roleId as SimRole;
  const [mod, setMod] = useState<SimModuleDetail | null>(null);
  const [session, setSession] = useState<SimulationSessionRecord | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      fetchSimulationModule(roleId).then((r) => setMod(r.module)),
      fetchSimulationSession(roleId)
        .then((r) => setSession(r.session))
        .catch(() => startSimulationSession(roleId).then((r) => setSession(r.session))),
    ]).catch((err) => setError(getAuthErrorMessage(err)));
  }, [roleId]);

  if (error) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <p className="text-destructive">{error}</p>
        <Button asChild className="mt-4" variant="outline">
          <Link href="/roles">Back to roles</Link>
        </Button>
      </div>
    );
  }

  if (!mod || !session) {
    return <p className="p-10 text-center text-muted-foreground">Loading simulation…</p>;
  }

  const taskById = new Map(mod.tasks.map((t) => [t.id, t]));

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href="/roles">
          <ArrowLeft className="h-4 w-4" /> All simulations
        </Link>
      </Button>

      <header>
        <Badge className="mb-2">{mod.company}</Badge>
        <h1 className="text-2xl font-bold">{mod.label} simulation</h1>
        <p className="mt-1 text-muted-foreground">{mod.projectName}</p>
        <div className="mt-4">
          <Progress value={session.progressPercent} />
          <p className="mt-1 text-xs text-muted-foreground">
            {session.tasksCompleted} of {session.totalTasks} tasks passed
            {session.status === 'completed' && ' — module complete!'}
          </p>
        </div>
      </header>

      <ol className="space-y-3">
        {session.tasks.map((tp, i) => {
          const task = taskById.get(tp.taskId);
          if (!task) return null;

          const icon =
            tp.status === 'passed' ? (
              <CheckCircle2 className="h-5 w-5 text-primary" />
            ) : tp.status === 'locked' ? (
              <Lock className="h-5 w-5 text-muted-foreground" />
            ) : (
              <Circle className="h-5 w-5 text-muted-foreground" />
            );

          return (
            <li key={tp.taskId}>
              <Card className={tp.status === 'locked' ? 'opacity-60' : ''}>
                <CardHeader className="flex flex-row items-start gap-3 pb-2">
                  {icon}
                  <div className="flex-1">
                    <p className="text-xs text-muted-foreground">Task {i + 1}</p>
                    <CardTitle className="text-base">{task.title}</CardTitle>
                    <CardDescription className="mt-1">{task.instruction}</CardDescription>
                  </div>
                  {tp.score !== null && (
                    <Badge variant={tp.status === 'passed' ? 'default' : 'outline'}>
                      {tp.score}%
                    </Badge>
                  )}
                </CardHeader>
                <CardContent className="pl-11">
                  {tp.status === 'locked' ? (
                    <p className="text-xs text-muted-foreground">Complete the previous task first.</p>
                  ) : (
                    <Button asChild size="sm" variant={tp.status === 'passed' ? 'outline' : 'default'}>
                      <Link href={`/roles/${roleId}/tasks/${tp.taskId}`}>
                        {tp.status === 'passed'
                          ? 'Review submission'
                          : tp.status === 'needs_revision'
                            ? 'Revise & resubmit'
                            : 'Open task'}
                      </Link>
                    </Button>
                  )}
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function RoleModulePage() {
  return (
    <AuthGuard>
      <ModuleContent />
    </AuthGuard>
  );
}
