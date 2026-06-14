import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { CreateLabRunRequest, LabRunRecord } from './types';

let admin: SupabaseClient | null = null;

export function getSupabaseAdmin(): SupabaseClient | null {
  const url = process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return null;
  if (!admin) {
    admin = createClient(url, key, { auth: { persistSession: false } });
  }
  return admin;
}

export function proofUrlForId(id: string): string {
  const base = process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3200';
  return `${base.replace(/\/$/, '')}/lab/proof/${id}`;
}

export async function createLabRun(body: CreateLabRunRequest): Promise<LabRunRecord | null> {
  const sb = getSupabaseAdmin();
  if (!sb) return null;

  const { data, error } = await sb
    .from('lab_runs')
    .insert({
      lab_slug: body.lab_slug,
      title: body.title,
      summary: body.summary,
      bullets: body.bullets ?? [],
      metrics: body.metrics ?? {},
      provider: body.provider ?? null,
      model: body.model ?? null,
    })
    .select('*')
    .single();

  if (error || !data) return null;
  return data as LabRunRecord;
}

export async function getLabRun(id: string): Promise<LabRunRecord | null> {
  const sb = getSupabaseAdmin();
  if (!sb) return null;

  const { data, error } = await sb.from('lab_runs').select('*').eq('id', id).maybeSingle();
  if (error || !data) return null;
  return data as LabRunRecord;
}
