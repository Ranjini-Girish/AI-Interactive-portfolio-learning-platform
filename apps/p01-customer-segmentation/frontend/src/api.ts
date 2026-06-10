/** Use Vite proxy in dev (/api → :8000). Override with VITE_API_URL for production. */
const API_BASE = import.meta.env.VITE_API_URL ?? '/api';

export type UploadSummary = {
  row_count: number;
  columns: string[];
  stats: Record<string, { min: number; max: number; mean: number }>;
};

export type CustomerSegment = {
  customer_id: string;
  txn_count: number;
  avg_balance: number;
  monthly_spend: number;
  segment_id: number;
  segment_name: string;
};

export type SegmentResult = {
  customers: CustomerSegment[];
  centroids: {
    segment_id: number;
    segment_name: string;
    txn_count: number;
    avg_balance: number;
    monthly_spend: number;
  }[];
  metrics: {
    k: number;
    silhouette_score: number;
    inertia: number;
  };
};

const OFFLINE_MSG =
  'Could not connect to the data service. Double-click START-PORTFOLIO.bat (or ask your instructor to start the P01 backend on port 8000), then refresh this page.';

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new Error(OFFLINE_MSG);
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const detail = body.detail ?? res.statusText;
    return typeof detail === 'string' ? detail : res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await apiFetch('/health');
    if (!res.ok) return false;
    const data = await res.json();
    return data.ok === true;
  } catch {
    return false;
  }
}

export async function loadSampleDataset(): Promise<UploadSummary> {
  let res = await apiFetch('/sample/load', { method: 'POST' });
  if (res.status === 404) {
    // Backend not restarted yet — load CSV from Vite public folder and upload
    const csvRes = await fetch('/sample/customers.csv');
    if (!csvRes.ok) {
      throw new Error(
        'Sample load failed. Restart the P01 API (port 8000) or upload data/customers.csv manually.',
      );
    }
    const blob = await csvRes.blob();
    const file = new File([blob], 'customers.csv', { type: 'text/csv' });
    return uploadCsv(file);
  }
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function uploadCsv(file: File): Promise<UploadSummary> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiFetch('/upload', { method: 'POST', body: form });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function runSegmentation(k: number): Promise<SegmentResult> {
  const res = await apiFetch('/segment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ k }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
