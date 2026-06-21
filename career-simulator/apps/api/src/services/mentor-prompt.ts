import { env } from '../config/env';
import { getLatestJobMatch } from '../repositories/job-repository';
import { getLatestAnalysis } from '../repositories/resume-repository';

export const MENTOR_SYSTEM_PROMPT = `You are a senior work mentor helping beginners, career returners, and upskillers practice real company jobs.

YOUR PERSONALITY
- Warm, patient, and encouraging — like a helpful colleague on their first week.
- Speak simple English. Define any jargon the first time you use it.
- Always include a real-world analogy or example.
- Break answers into numbered steps when explaining tasks.
- End with one concrete "try this next" action when appropriate.

RULES
- Never assume prior tech knowledge.
- Keep responses focused (2–4 short paragraphs unless the user asks for depth).
- Tie advice to their resume skills and job goals when context is provided.
- If they ask about APIs, use the restaurant ordering analogy: customer (app) → waiter (API) → kitchen (server).
- Do not make up credentials or job offers. You are a learning coach, not a recruiter.

When reviewing work, praise what is good first, then suggest 1–2 specific improvements.`;

export async function buildMentorContextBlock(userId: string): Promise<string> {
  const parts: string[] = [];

  const resume = await getLatestAnalysis(userId);
  if (resume) {
    const a = resume.analysis;
    const top = a.jobMatchScores[0];
    parts.push(
      `RESUME CONTEXT: ${a.headline}`,
      `Skills: ${a.skills.slice(0, 12).join(', ')}`,
      `Experience: ${a.experienceYears ?? 'unknown'} years`,
      `Best role fit: ${top?.label ?? 'unknown'} (${top?.score ?? 0}%)`,
      `Learning roadmap steps: ${a.learningRoadmap.map((s) => s.title).join('; ')}`,
    );
  }

  const job = await getLatestJobMatch(userId);
  if (job) {
    const m = job.analysis;
    parts.push(
      `JOB TARGET: ${m.jobTitle}`,
      `Match score: ${m.overallMatchScore}%`,
      `Gaps: ${m.skillGaps.slice(0, 6).join(', ') || 'none major'}`,
      `Missing tools: ${m.missingTools.join(', ') || 'none'}`,
    );
  }

  if (parts.length === 0) {
    return 'USER CONTEXT: New user — no resume or job match yet. Guide them to upload a resume first.';
  }

  return `USER CONTEXT (use to personalize, do not repeat verbatim):\n${parts.join('\n')}`;
}

export function isMentorConfigured(): boolean {
  return Boolean(env.OPENAI_API_KEY?.trim());
}

export function getMentorModel(): string {
  return env.OPENAI_MODEL;
}
