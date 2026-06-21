import type { ProgressWeakArea } from '@career-sim/shared';
import { AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const SOURCE_LABEL: Record<ProgressWeakArea['source'], string> = {
  resume: 'Resume',
  job_match: 'Job',
  simulation: 'Practice',
  tools: 'Tools',
};

export function WeakAreasCard({ areas }: { areas: ProgressWeakArea[] }) {
  if (!areas.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Weak areas</CardTitle>
          <CardDescription>No major gaps flagged — keep practicing simulations.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          Weak areas
        </CardTitle>
        <CardDescription>Focus here to raise your readiness score fastest</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3">
          {areas.map((area) => (
            <li key={area.id} className="flex items-start justify-between gap-2 text-sm">
              <div>
                <p className="font-medium">{area.label}</p>
                {area.detail && <p className="text-xs text-muted-foreground">{area.detail}</p>}
              </div>
              <Badge variant="outline" className="shrink-0 text-xs">
                {SOURCE_LABEL[area.source]}
              </Badge>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
