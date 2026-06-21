import type { ProgressDashboard } from '@career-sim/shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function DashboardStats({ stats }: { stats: ProgressDashboard['stats'] }) {
  const items = [
    { label: 'Skills identified', value: stats.skillsIdentified },
    { label: 'Skills practiced', value: stats.skillsPracticed },
    { label: 'Tasks passed', value: `${stats.tasksCompleted}/${stats.totalSimulationTasks}` },
    { label: 'Modules done', value: `${stats.modulesCompleted}/${stats.totalModules}` },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <Card key={item.label}>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">{item.label}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold tabular-nums">{item.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
