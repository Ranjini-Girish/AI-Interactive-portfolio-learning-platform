'use client';

import type { HealthResponse } from '@career-sim/shared';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

const DEPLOY_STEPS = [
  { label: 'API on Render', detail: 'Dockerfile.api + render.yaml + managed Postgres' },
  { label: 'Web on Vercel', detail: 'apps/web with NEXT_PUBLIC_API_URL' },
  { label: 'CORS_ORIGIN', detail: 'Set Vercel URL on Render API service' },
];

export function DeployChecklist({ health }: { health: HealthResponse | null }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Deployment (Phase 10)</CardTitle>
          <Badge variant={health?.deploy === 'production_ready' ? 'default' : 'outline'}>
            {health?.deploy === 'production_ready' ? 'API deploy-ready' : 'Local dev'}
          </Badge>
        </div>
        <CardDescription>
          Production: Vercel (web) + Render (API + Postgres). See PHASE-10.md.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm text-muted-foreground">
          {DEPLOY_STEPS.map((s) => (
            <li key={s.label}>
              <span className="font-medium text-foreground">{s.label}</span> — {s.detail}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
