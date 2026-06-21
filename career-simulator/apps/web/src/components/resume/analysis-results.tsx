'use client';

import Link from 'next/link';
import type { ResumeAnalysisRecord } from '@career-sim/shared';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

export function ResumeAnalysisView({ record }: { record: ResumeAnalysisRecord }) {
  const { analysis: a } = record;
  const top = a.jobMatchScores[0];

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Badge variant="secondary">Analysis saved</Badge>
        <h2 className="text-xl font-semibold">Your resume intelligence report</h2>
        <p className="text-sm text-muted-foreground">{a.headline}</p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Best job match</CardTitle>
            <CardDescription>{top?.label ?? 'Run analysis'}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{top?.score ?? 0}%</p>
            <Progress value={top?.score ?? 0} className="mt-2" />
            <p className="mt-2 text-xs text-muted-foreground">{top?.rationale}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Experience detected</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {a.experienceYears != null ? `${a.experienceYears} yrs` : '—'}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">{a.skills.length} skills identified</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Skills found</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {a.skills.map((s) => (
            <Badge key={s} variant="outline">
              {s}
            </Badge>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Strengths</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {a.strengths.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Gaps to close</CardTitle>
          </CardHeader>
          <CardContent>
            {a.gaps.length === 0 ? (
              <p className="text-sm text-muted-foreground">No major gaps for your top role.</p>
            ) : (
              <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                {a.gaps.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Job match scores (all roles)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {a.jobMatchScores.map((j) => (
            <div key={j.role}>
              <div className="mb-1 flex justify-between text-sm">
                <span>{j.label}</span>
                <span className="font-medium">{j.score}%</span>
              </div>
              <Progress value={j.score} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Learning roadmap</CardTitle>
          <CardDescription>Step-by-step path your AI mentor will guide you through</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {a.learningRoadmap.map((step) => (
            <div key={step.step} className="rounded-lg border border-border p-3">
              <p className="text-xs font-medium text-primary">
                Step {step.step} · ~{step.estimatedDays} days
              </p>
              <p className="font-medium">{step.title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Suggested practice projects</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {a.practiceProjects.map((p) => (
            <div key={p.title} className="rounded-lg bg-muted/40 p-3 text-sm">
              <p className="font-medium">{p.title}</p>
              <p className="mt-1 text-muted-foreground">{p.description}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      {a.projects.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Projects from your resume</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {a.projects.map((p) => (
              <div key={p.name + p.description.slice(0, 20)}>
                <p className="font-medium text-sm">{p.name}</p>
                <p className="text-sm text-muted-foreground">{p.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Button asChild>
        <Link href="/dashboard">Back to dashboard</Link>
      </Button>
    </div>
  );
}
