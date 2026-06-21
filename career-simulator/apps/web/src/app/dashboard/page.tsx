'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { ProgressDashboard } from '@career-sim/shared';
import { AuthGuard } from '@/components/auth/auth-guard';
import { DashboardStats } from '@/components/dashboard/dashboard-stats';
import { LearningPathProgress } from '@/components/dashboard/learning-path-progress';
import { ModulesGrid } from '@/components/dashboard/modules-grid';
import { NextStepsCard } from '@/components/dashboard/next-steps';
import { ReadinessHero } from '@/components/dashboard/readiness-hero';
import { SkillsPanel } from '@/components/dashboard/skills-panel';
import { WeakAreasCard } from '@/components/dashboard/weak-areas';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { fetchProgressDashboard } from '@/lib/api-client';

function DashboardContent() {
  const [data, setData] = useState<ProgressDashboard | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchProgressDashboard()
      .then(setData)
      .catch(() => setError('Could not load dashboard. Is the API running with PostgreSQL?'));
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <p className="text-destructive">{error}</p>
      </div>
    );
  }

  if (!data) {
    return <p className="p-10 text-center text-muted-foreground">Loading your progress…</p>;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-10">
      <header>
        <Badge className="mb-2">Phase 9 — Interviews</Badge>
        <h1 className="text-2xl font-bold">Your progress</h1>
        <p className="mt-2 text-muted-foreground">{data.message}</p>
      </header>

      <ReadinessHero readiness={data.readiness} />

      <DashboardStats stats={data.stats} />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Project completion</CardTitle>
          <CardDescription>Average progress across all simulation modules</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-end justify-between gap-4">
            <span className="text-3xl font-bold tabular-nums">{data.stats.projectCompletionPercent}%</span>
            <span className="pb-1 text-sm text-muted-foreground">
              {data.stats.modulesCompleted} of {data.stats.totalModules} modules finished
            </span>
          </div>
          <Progress value={data.stats.projectCompletionPercent} className="mt-3" />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <NextStepsCard steps={data.nextSteps} />
        <WeakAreasCard areas={data.weakAreas} />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <div>
            <CardTitle className="text-base">Mock interview</CardTitle>
            <CardDescription>Behavioral + technical practice with scoring</CardDescription>
          </div>
          <Button asChild size="sm" variant="outline">
            <Link href="/interview">Practice</Link>
          </Button>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <div>
            <CardTitle className="text-base">Portfolio generator</CardTitle>
            <CardDescription>Resume bullets, LinkedIn copy, and GitHub README</CardDescription>
          </div>
          <Button asChild size="sm">
            <Link href="/portfolio">Open</Link>
          </Button>
        </CardHeader>
      </Card>

      <SkillsPanel skills={data.skillsLearned} />

      <div className="grid gap-6 lg:grid-cols-2">
        <ModulesGrid modules={data.modules} />
        <LearningPathProgress steps={data.learningPath} />
      </div>

      {(data.resume || data.jobMatch) && (
        <div className="grid gap-4 sm:grid-cols-2">
          {data.resume && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Resume</CardTitle>
                <CardDescription>{data.resume.headline}</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between">
                <p className="text-sm">
                  Top role: <strong>{data.resume.topRole}</strong> ({data.resume.topScore}%)
                </p>
                <Button asChild size="sm" variant="outline">
                  <Link href="/resume">View</Link>
                </Button>
              </CardContent>
            </Card>
          )}
          {data.jobMatch && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Job match</CardTitle>
                <CardDescription>{data.jobMatch.jobTitle}</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between">
                <p className="text-sm">
                  <strong>{data.jobMatch.matchScore}%</strong> · {data.jobMatch.gapCount} gaps
                </p>
                <Button asChild size="sm" variant="outline">
                  <Link href="/job">View</Link>
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {data.activeSimulation && (
        <Card className="border-primary/20 bg-primary/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Active simulation — {data.activeSimulation.label}</CardTitle>
          </CardHeader>
          <CardContent>
            <Progress value={data.activeSimulation.progressPercent} className="mb-2" />
            <p className="text-sm text-muted-foreground">
              {data.activeSimulation.tasksCompleted}/{data.activeSimulation.totalTasks} tasks passed
            </p>
            <Button asChild size="sm" className="mt-3">
              <Link href={`/roles/${data.activeSimulation.roleId}`}>Continue</Link>
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  );
}
