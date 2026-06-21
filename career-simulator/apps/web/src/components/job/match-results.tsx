'use client';

import Link from 'next/link';
import type { JobMatchRecord } from '@career-sim/shared';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

export function JobMatchResults({ record }: { record: JobMatchRecord }) {
  const a = record.analysis;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Badge variant="secondary">Match saved</Badge>
        <h2 className="text-xl font-semibold">{a.jobTitle}</h2>
        <p className="text-sm text-muted-foreground">{a.plainSummary}</p>
      </header>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Overall match score</CardTitle>
          <CardDescription>Your resume vs this job posting</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-4xl font-bold">{a.overallMatchScore}%</p>
          <Progress value={a.overallMatchScore} className="mt-3" />
          <p className="mt-2 text-xs text-muted-foreground">
            {a.matchedSkills.length} skills match · {a.skillGaps.length} gaps ·{' '}
            {a.missingTools.length} tools to learn
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-emerald-600 dark:text-emerald-400">
              You already have
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {a.matchedSkills.length === 0 ? (
              <p className="text-sm text-muted-foreground">No direct matches yet — follow the learning path below.</p>
            ) : (
              a.matchedSkills.map((s) => (
                <Badge key={s} variant="default">
                  {s}
                </Badge>
              ))
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-amber-600 dark:text-amber-400">Skill gaps</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {a.skillGaps.length === 0 ? (
              <p className="text-sm text-muted-foreground">No major skill gaps — great alignment!</p>
            ) : (
              a.skillGaps.map((s) => (
                <Badge key={s} variant="outline">
                  {s}
                </Badge>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {a.missingTools.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Missing tools</CardTitle>
            <CardDescription>Software mentioned in the JD that isn&apos;t on your resume yet</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {a.missingTools.map((t) => (
              <Badge key={t} variant="secondary">
                {t}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Required by employer</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {a.requiredSkills.map((s) => (
            <Badge key={s} variant="outline">
              {s}
            </Badge>
          ))}
        </CardContent>
      </Card>

      {a.preferredSkills.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Nice to have</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {a.preferredSkills.map((s) => (
              <Badge key={s} variant="outline">
                {s}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Suggested learning path</CardTitle>
          <CardDescription>Close gaps before you apply — your mentor will guide each step in Phase 5+</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {a.learningPath.map((step) => (
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

      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link href="/dashboard">Dashboard</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/roles">Start job simulation</Link>
        </Button>
      </div>
    </div>
  );
}
