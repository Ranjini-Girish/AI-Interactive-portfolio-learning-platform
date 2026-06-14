export type LabRunRecord = {
  id: string;
  lab_slug: string;
  title: string;
  summary: string;
  bullets: string[];
  metrics: Record<string, unknown>;
  provider: string | null;
  model: string | null;
  created_at: string;
};

export type CreateLabRunRequest = {
  lab_slug: string;
  title: string;
  summary: string;
  bullets?: string[];
  metrics?: Record<string, unknown>;
  provider?: string | null;
  model?: string | null;
};

export type CreateLabRunResponse = {
  id: string;
  proof_url: string;
};
