import { NextResponse } from 'next/server';
import {
  buildLocalMentorReply,
  type MentorRequest,
} from '@/lib/mentor';

async function callOpenAIMentor(req: MentorRequest): Promise<string | null> {
  const key = process.env.OPENAI_API_KEY;
  if (!key) return null;

  const system = `You are a senior AI/ML engineering mentor helping Ranjini Gowda build portfolio projects from her resume. Be concise, actionable, and specific. Reference the current step instruction. Do not write full solutions — guide with checkpoints, commands, and architecture tips.`;

  const user = JSON.stringify({
    project: req.projectTitle,
    step: req.step.title,
    instruction: req.step.instruction,
    checklist: req.step.verifyChecklist,
    completed: req.completedChecklist,
    question: req.userMessage,
    notes: req.note,
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
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
        temperature: 0.4,
        max_tokens: 800,
      }),
    });

    if (!res.ok) return null;
    const data = await res.json();
    return data.choices?.[0]?.message?.content ?? null;
  } catch {
    return null;
  }
}

export async function POST(request: Request) {
  const body = (await request.json()) as MentorRequest;
  const local = buildLocalMentorReply(body);
  const llm = await callOpenAIMentor(body);

  if (llm) {
    return NextResponse.json({
      ...local,
      reply: llm,
      source: 'openai',
    });
  }

  return NextResponse.json({ ...local, source: 'local' });
}
