import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const key = process.env.OPENAI_API_KEY;
  if (!key) {
    return NextResponse.json(
      { error: 'OPENAI_API_KEY not set — use Browser voice or add key to .env.local' },
      { status: 503 },
    );
  }

  let body: { text?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const text = body.text?.trim();
  if (!text || text.length > 4096) {
    return NextResponse.json({ error: 'text required (max 4096 chars)' }, { status: 422 });
  }

  const model = process.env.OPENAI_TTS_MODEL ?? 'tts-1';
  const voice = process.env.OPENAI_TTS_VOICE ?? 'nova';

  const res = await fetch('https://api.openai.com/v1/audio/speech', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      voice,
      input: text,
      response_format: 'mp3',
    }),
  });

  if (!res.ok) {
    return NextResponse.json({ error: 'OpenAI TTS request failed' }, { status: 502 });
  }

  const audio = await res.arrayBuffer();
  return new NextResponse(audio, {
    headers: {
      'Content-Type': 'audio/mpeg',
      'Cache-Control': 'no-store',
    },
  });
}
