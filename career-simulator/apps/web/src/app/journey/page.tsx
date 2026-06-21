import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

const STEPS = [
  { id: 1, label: 'Upload resume', phase: 3, status: 'done' },
  { id: 2, label: 'Paste job description', phase: 4, status: 'done' },
  { id: 3, label: 'Review learning plan', phase: 4, status: 'done' },
  { id: 4, label: 'AI mentor guidance', phase: 5, status: 'done' },
  { id: 5, label: 'Start simulation', phase: 6, status: 'done' },
  { id: 6, label: 'Track progress & portfolio', phase: 7, status: 'done' },
  { id: 7, label: 'Build portfolio', phase: 8, status: 'done' },
  { id: 8, label: 'Mock interview practice', phase: 9, status: 'done' },
  { id: 9, label: 'Deploy to production', phase: 10, status: 'done' },
];

export default function JourneyPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-10">
      <header>
        <Badge className="mb-3">Wizard preview</Badge>
        <h1 className="text-2xl font-bold">Your guided journey</h1>
        <p className="mt-2 text-muted-foreground">
          Step-by-step workflow — each step unlocks after the previous one. Full wizard ships in
          Phases 3–6.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sample user</CardTitle>
          <CardDescription>
            Career returner · QA background · 3 years experience · restarting after a gap
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>Target roles: QA Tester, Data Analyst, Project Coordinator</p>
          <p>Try resume + job match flows at /resume and /job</p>
        </CardContent>
      </Card>

      <ol className="space-y-4">
        {STEPS.map((step, i) => (
          <li key={step.id}>
            <Card className="opacity-80">
              <CardHeader className="flex flex-row items-start justify-between gap-4 pb-2">
                <div>
                  <p className="text-xs text-muted-foreground">Step {step.id}</p>
                  <CardTitle className="text-base">{step.label}</CardTitle>
                </div>
                <Badge variant="outline">Phase {step.phase}</Badge>
              </CardHeader>
              <CardContent>
                <Progress value={0} />
                <p className="mt-2 text-xs text-muted-foreground">
                  {i === 0
                    ? 'Done — /resume'
                    : i === 1 || i === 2
                      ? 'Done — /job (match sample JD or paste your own)'
                      : i === 3
                        ? 'Done — mentor sidebar / mobile bot'
                        : i === 4
                          ? 'Live — /roles (QA, Data Analyst, PM, AI Reviewer)'
                          : i === 5
                            ? 'Done — /dashboard (readiness, weak areas, next steps)'
                            : i === 6
                              ? 'Done — /portfolio (resume bullets, LinkedIn, GitHub README)'
                              : i === 7
                                ? 'Live — /interview (behavioral + technical, scored feedback)'
                                : i === 8
                                  ? 'See PHASE-10.md — Vercel + Render deployment'
                                  : 'Locked until prior steps complete'}
                </p>
              </CardContent>
            </Card>
          </li>
        ))}
      </ol>
    </div>
  );
}
