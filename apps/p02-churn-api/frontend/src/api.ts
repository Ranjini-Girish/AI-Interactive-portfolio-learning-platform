const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8001';

export type Health = {
  ok: boolean;
  db_ok: boolean;
  model_loaded: boolean;
  model_version: string | null;
};

export type CustomerInput = {
  customer_id: string;
  tenure_months: number;
  monthly_charges: number;
  total_charges: number;
  contract_type: 'month' | 'year' | 'two_year';
  support_calls: number;
};

export type Prediction = {
  customer_id: string;
  churn_probability: number;
  risk_band: 'low' | 'medium' | 'high';
  model_version: string;
  top_drivers: { feature: string; impact: number; direction: string }[];
};

export type LogItem = {
  id: number;
  created_at: string;
  customer_id: string;
  churn_probability: number;
  risk_band: string;
  model_version: string;
};

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg: string }) => d.msg).join('; ');
    }
    return res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function predictOne(customer: CustomerInput): Promise<Prediction> {
  const res = await fetch(`${API_BASE}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(customer),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function predictBatch(customers: CustomerInput[]): Promise<Prediction[]> {
  const res = await fetch(`${API_BASE}/predict/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customers }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.predictions;
}

export async function fetchHistory(page = 1, pageSize = 50): Promise<LogItem[]> {
  const res = await fetch(`${API_BASE}/predictions?page=${page}&page_size=${pageSize}`);
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.items;
}
