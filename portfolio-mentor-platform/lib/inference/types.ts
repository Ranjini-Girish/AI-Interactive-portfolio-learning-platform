export type SegmentCentroid = {
  segment_id: number;
  segment_name: string;
  txn_count: number;
  avg_balance: number;
  monthly_spend: number;
};

export type SegmentMetrics = {
  k: number;
  silhouette_score: number;
  inertia?: number;
};

export type SummarizeSegmentsRequest = {
  segments: {
    centroids: SegmentCentroid[];
    metrics: SegmentMetrics;
  };
  company?: string;
};

export type SummarizeSegmentsResponse = {
  summary: string;
  bullets: string[];
  source: 'huggingface' | 'local';
  model: string | null;
  provider: 'huggingface' | 'local';
};

export type EmbedRequest = {
  texts: string[];
};

export type EmbedResponse = {
  embeddings: number[][];
  model: string | null;
  provider: 'huggingface' | 'local';
  dimensions: number;
};

export type RagDocument = {
  id: string;
  text: string;
};

export type RagSearchRequest = {
  query: string;
  documents: RagDocument[];
  top_k?: number;
};

export type RagSearchHit = {
  id: string;
  text: string;
  score: number;
};

export type RagSearchResponse = {
  hits: RagSearchHit[];
  model: string | null;
  provider: 'huggingface' | 'local';
};
