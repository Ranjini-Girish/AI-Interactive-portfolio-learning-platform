'use client';

import { useEffect, useState } from 'react';
import type { HealthResponse } from '@career-sim/shared';
import { API_URL, fetchHealth } from '@/lib/api-client';
import { DeployChecklist } from '@/components/home/deploy-checklist';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

function apiOfflineMessage(): string {
  const isLocal =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
  if (isLocal) {
    return 'Start the API: npm run dev:api (port 4000)';
  }
  return `Backend not reachable at ${API_URL}. Deploy the API on Fly.io (see FLY-DEPLOY.md).`;
}

export function SystemStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setError(apiOfflineMessage()));
  }, []);

  return (
    <Card className="border-primary/20 bg-primary/5">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">System status</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-3 text-sm">
        {error ? (
          <Badge variant="outline" className="text-destructive">
            API offline — {error}
          </Badge>
        ) : !health ? (
          <span className="text-muted-foreground">Checking API…</span>
        ) : (
          <>
            <Badge variant={health.ok ? 'default' : 'outline'}>
              API {health.ok ? 'online' : 'degraded'}
            </Badge>
            <Badge variant="secondary">Phase {health.phase}</Badge>
            <Badge variant="outline">DB: {health.database ?? 'unknown'}</Badge>
            <Badge variant="outline">Auth: {health.auth ?? 'unknown'}</Badge>
            <Badge variant="outline">Mentor: {health.mentor ?? 'unknown'}</Badge>
            <Badge variant="outline">Simulation: {health.simulation ?? 'unknown'}</Badge>
            <Badge variant="outline">Portfolio: {health.portfolio ?? 'unknown'}</Badge>
            <Badge variant="outline">Interview: {health.interview ?? 'unknown'}</Badge>
            <Badge variant="outline">Deploy: {health.deploy ?? 'unknown'}</Badge>
          </>
        )}
      </CardContent>
      {health && !error && (
        <div className="px-6 pb-4">
          <DeployChecklist health={health} />
        </div>
      )}
    </Card>
  );
}
