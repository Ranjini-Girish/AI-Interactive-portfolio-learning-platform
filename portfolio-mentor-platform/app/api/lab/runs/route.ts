import { inferenceCorsHeaders, jsonWithCors } from '@/lib/inference/cors';
import { createLabRun, proofUrlForId } from '@/lib/lab/store';
import type { CreateLabRunRequest } from '@/lib/lab/types';

export async function OPTIONS() {
  return new Response(null, { status: 204, headers: inferenceCorsHeaders });
}

export async function POST(request: Request) {
  const body = (await request.json()) as CreateLabRunRequest;

  if (!body.lab_slug?.trim() || !body.title?.trim() || !body.summary?.trim()) {
    return jsonWithCors(
      { error: 'lab_slug, title, and summary are required' },
      { status: 400 },
    );
  }

  const record = await createLabRun(body);
  if (!record) {
    return jsonWithCors(
      {
        error:
          'Lab storage unavailable. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (run supabase/schema.sql first).',
      },
      { status: 503 },
    );
  }

  return jsonWithCors({
    id: record.id,
    proof_url: proofUrlForId(record.id),
  });
}
