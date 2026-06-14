export type SupabaseServiceCheck = {
  configured: boolean;
  url_preview: string | null;
  can_write: boolean;
  error: string | null;
};

export function getSupabaseUrl(): string | null {
  return process.env.SUPABASE_URL?.trim() || process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() || null;
}

export function getSupabaseServiceKey(): string | null {
  return process.env.SUPABASE_SERVICE_ROLE_KEY?.trim() || null;
}

export function maskUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.hostname.slice(0, 8)}…`;
  } catch {
    return 'invalid-url';
  }
}
