import { NextResponse } from 'next/server';
import { buildLocalSuggestion } from '@/lib/interview/local-coach';
import type { SuggestRequest, SuggestResponse } from '@/lib/interview/types';

function systemPrompt(round: string): string {
  return `You are a private interview coach. The candidate sees your output on a second screen during a live call.
Round type: ${round}.
Rules:
- Write speakable answers (60-120 seconds when read aloud).
- Ground every answer in THEIR resume and the job description provided.
- Recruiter: concise, motivated, culture fit.
- Technical: structured approach, trade-offs, metrics; no fake experience.
- Behavioral: STAR format.
- Never mention that you are an AI. Output JSON only:
{"answer":"...","bullets":["...","..."],"followUpTip":"..."}`;
}

async function callOpenAI(req: SuggestRequest): Promise<SuggestResponse | null> {
  const key = req.userApiKey || process.env.OPENAI_API_KEY;
  if (!key) return null;

  const user = JSON.stringify({
    jobDescription: req.session.jobDescription.slice(0, 6000),
    resume: req.session.resume.slice(0, 6000),
    company: req.session.company,
    roleTitle: req.session.roleTitle,
    round: req.session.round,
    question: req.question,
    recentTranscript: req.transcriptTail?.slice(-500),
  });

  try {
    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${key}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL ?? 'gpt-4o-mini',
        messages: [
          { role: 'system', content: systemPrompt(req.session.round) },
          { role: 'user', content: user },
        ],
        temperature: 0.35,
        max_tokens: 700,
        response_format: { type: 'json_object' },
      }),
    });

    if (!res.ok) return null;
    const data = await res.json();
    const raw = data.choices?.[0]?.message?.content;
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Omit<SuggestResponse, 'source'>;
    return {
      answer: parsed.answer ?? '',
      bullets: Array.isArray(parsed.bullets) ? parsed.bullets : [],
      followUpTip: parsed.followUpTip ?? '',
      source: 'openai',
    };
  } catch {
    return null;
  }
}

export async function POST(request: Request) {
  const body = (await request.json()) as SuggestRequest;

  if (!body.question?.trim()) {
    return NextResponse.json({ error: 'Missing question' }, { status: 400 });
  }

  const llm = await callOpenAI(body);
  if (llm) {
    return NextResponse.json(llm);
  }

  return NextResponse.json(buildLocalSuggestion(body.session, body.question));
}
