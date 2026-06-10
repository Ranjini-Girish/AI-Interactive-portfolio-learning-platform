export type DemoStatus = 'live' | 'scaffolded' | 'planned';

export type DemoConfig = {
  slug: string;
  status: DemoStatus;
  localUrl: string;
  apiUrl?: string;
  apiDocsUrl?: string;
  startHint: string;
  startCommands: string;
};

function envUrl(key: string, fallback: string): string {
  if (typeof process !== 'undefined' && process.env[key]) {
    return process.env[key] as string;
  }
  return fallback;
}

export const demos: Record<string, DemoConfig> = {
  'customer-segmentation-lab': {
    slug: 'customer-segmentation-lab',
    status: 'scaffolded',
    localUrl: envUrl('NEXT_PUBLIC_DEMO_P01_URL', 'http://localhost:5173'),
    apiUrl: envUrl('NEXT_PUBLIC_API_P01_URL', 'http://localhost:8000'),
    apiDocsUrl: envUrl('NEXT_PUBLIC_API_P01_URL', 'http://localhost:8000') + '/docs',
    startHint: 'Beginner-friendly · practice data included · ports 8000 + 5173',
    startCommands:
      'cd apps/p01-customer-segmentation/backend\nuvicorn main:app --reload --port 8000\n\ncd apps/p01-customer-segmentation/frontend\nnpm run dev',
  },
  'churn-prediction-api': {
    slug: 'churn-prediction-api',
    status: 'scaffolded',
    localUrl: envUrl('NEXT_PUBLIC_DEMO_P02_URL', 'http://localhost:5174'),
    apiUrl: envUrl('NEXT_PUBLIC_API_P02_URL', 'http://localhost:8001'),
    apiDocsUrl: envUrl('NEXT_PUBLIC_API_P02_URL', 'http://localhost:8001') + '/docs',
    startHint: 'run train.py · backend :8001 · frontend :5174',
    startCommands:
      'cd apps/p02-churn-api/backend\npython train.py\nuvicorn main:app --reload --port 8001\n\ncd apps/p02-churn-api/frontend\nnpm run dev',
  },
  'hybrid-recommendation-engine': {
    slug: 'hybrid-recommendation-engine',
    status: 'scaffolded',
    localUrl: envUrl('NEXT_PUBLIC_DEMO_P03_URL', 'http://localhost:5175'),
    apiUrl: envUrl('NEXT_PUBLIC_API_P03_URL', 'http://localhost:8002'),
    apiDocsUrl: envUrl('NEXT_PUBLIC_API_P03_URL', 'http://localhost:8002') + '/health',
    startHint: 'python seed.py · backend :8002 · frontend :5175',
    startCommands:
      'cd apps/p03-recommendations/backend\npython seed.py\npython app.py\n\ncd apps/p03-recommendations/frontend\nnpm run dev',
  },
};

export function getDemo(slug: string): DemoConfig | undefined {
  return demos[slug];
}

export function scaffoldedCount(): number {
  return Object.values(demos).filter((d) => d.status === 'scaffolded' || d.status === 'live').length;
}
