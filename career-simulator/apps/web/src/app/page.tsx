import { DEVELOPMENT_PHASES, SIM_ROLES } from '@career-sim/shared';
import Link from 'next/link';
import { ArrowRight, CheckCircle2, Sparkles } from 'lucide-react';
import { SystemStatus } from '@/components/home/system-status';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

const JOURNEY_STEPS = [
  { step: 1, title: 'Upload resume', desc: 'PDF, Word, or paste text — we extract skills and projects.' },
  { step: 2, title: 'Choose job role', desc: 'QA, Data Analyst, PM, AI Reviewer, and more.' },
  { step: 3, title: 'Paste job description', desc: 'See skill gaps and a learning path matched to you.' },
  { step: 4, title: 'Get your plan', desc: 'Daily tasks, practice projects, and readiness score.' },
  { step: 5, title: 'Start simulation', desc: 'Do real company-style work with AI mentor guidance.' },
  { step: 6, title: 'Build portfolio', desc: 'Auto-generate bullets, LinkedIn copy, and interview prep.' },
];

export default function HomePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-10 px-4 py-10 sm:px-6">
      <section className="space-y-4 text-center">
        <Badge className="mx-auto">Phase 10 — Platform complete · deploy-ready</Badge>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          AI Career Transition &amp; Real-World Experience Simulator
        </h1>
        <p className="mx-auto max-w-2xl text-lg text-muted-foreground">
          Feel like you&apos;re actually working in a job while you learn. Built for non-IT beginners,
          career returners, freshers, and upskillers — with an AI mentor who explains everything in
          plain English.
        </p>
        <div className="flex flex-wrap justify-center gap-3 pt-2">
          <Button asChild size="lg">
            <Link href="/journey">
              See your journey <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/register">Create free account</Link>
          </Button>
        </div>
      </section>

      <SystemStatus />

      <section className="grid gap-4 sm:grid-cols-2">
        {SIM_ROLES.map((role) => (
          <Card key={role.id}>
            <CardHeader>
              <CardTitle className="text-base">{role.label}</CardTitle>
              <CardDescription>{role.description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>

      <section>
        <h2 className="mb-4 flex items-center gap-2 text-xl font-semibold">
          <Sparkles className="h-5 w-5 text-primary" />
          How it works (6 steps)
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {JOURNEY_STEPS.map((s) => (
            <Card key={s.step} className="relative overflow-hidden">
              <CardHeader className="pb-2">
                <p className="text-xs font-medium text-primary">Step {s.step}</p>
                <CardTitle className="text-base">{s.title}</CardTitle>
                <CardDescription>{s.desc}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Development roadmap</h2>
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Overall progress</span>
              <span className="font-medium">100%</span>
            </div>
            <Progress value={100} />
            <ul className="space-y-2 text-sm">
              {DEVELOPMENT_PHASES.map((p) => (
                <li key={p.id} className="flex items-center gap-2 text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                  <span>
                    Phase {p.id}: {p.name}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
