'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, CheckCircle2, Lock, PlayCircle } from 'lucide-react';
import type { SimModuleOverview, SimRole } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { getAuthErrorMessage } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { fetchSimulationModules, startSimulationSession } from '@/lib/api-client';

function RolesContent() {
  const [modules, setModules] = useState<SimModuleOverview[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState<SimRole | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchSimulationModules()
      .then((r) => setModules(r.modules))
      .catch((err) => setError(getAuthErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  async function handleStart(roleId: SimRole) {
    setError('');
    setStarting(roleId);
    try {
      await startSimulationSession(roleId);
      window.location.href = `/roles/${roleId}`;
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setStarting(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-10">
      <header>
        <Badge className="mb-2">Phase 6 — Job simulations</Badge>
        <h1 className="text-2xl font-bold">Real-world job simulations</h1>
        <p className="mt-2 text-muted-foreground">
          Pick a role and complete company-style tasks — test cases, bug reports, data insights,
          sprint plans, and AI quality reviews. Your AI mentor can help in the sidebar.
        </p>
      </header>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {loading && <p className="text-sm text-muted-foreground">Loading modules…</p>}

      <div className="grid gap-6">
        {modules.map((mod) => {
          const session = mod.session;
          const started = Boolean(session);
          const completed = session?.status === 'completed';

          return (
            <Card key={mod.roleId}>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle>{mod.label}</CardTitle>
                  {completed ? (
                    <Badge className="gap-1">
                      <CheckCircle2 className="h-3 w-3" /> Completed
                    </Badge>
                  ) : started ? (
                    <Badge variant="secondary">In progress</Badge>
                  ) : (
                    <Badge variant="outline">4 tasks</Badge>
                  )}
                </div>
                <CardDescription>
                  {mod.company} · {mod.projectName}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">{mod.description}</p>
                {session && (
                  <div>
                    <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                      <span>Progress</span>
                      <span>
                        {session.tasksCompleted}/{session.totalTasks} tasks
                      </span>
                    </div>
                    <Progress value={session.progressPercent} />
                  </div>
                )}
                <div className="flex flex-wrap gap-2">
                  {started ? (
                    <Button asChild>
                      <Link href={`/roles/${mod.roleId}`}>
                        Continue <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  ) : (
                    <Button
                      disabled={starting === mod.roleId}
                      onClick={() => handleStart(mod.roleId)}
                    >
                      <PlayCircle className="h-4 w-4" />
                      {starting === mod.roleId ? 'Starting…' : 'Start simulation'}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="border-dashed">
        <CardContent className="flex items-start gap-3 pt-6 text-sm text-muted-foreground">
          <Lock className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            Tasks unlock one at a time. Submit your work for instant feedback — revise and resubmit
            until you pass, then move to the next task.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default function RolesPage() {
  return (
    <AuthGuard>
      <RolesContent />
    </AuthGuard>
  );
}
