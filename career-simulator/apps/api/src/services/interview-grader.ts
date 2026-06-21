import OpenAI from 'openai';
import { z } from 'zod';
import type { InterviewAnswerFeedback, InterviewQuestionType, SimRole } from '@career-sim/shared';
import { env } from '../config/env';
import { getLatestJobMatch } from '../repositories/job-repository';
import { getLatestAnalysis } from '../repositories/resume-repository';
import { getMentorModel, isMentorConfigured } from './mentor-prompt';

const feedbackSchema = z.object({
  score: z.number().min(0).max(100),
  strengths: z.array(z.string()).min(1),
  improvements: z.array(z.string()).min(1),
  sampleOutline: z.string(),
});

function wordCount(text: string) {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function gradeBehavioralLocal(answer: string): InterviewAnswerFeedback {
  const words = wordCount(answer);
  let score = 0;
  const strengths: string[] = [];
  const improvements: string[] = [];

  if (words >= 60) {
    score += 25;
    strengths.push('Good length — enough detail for an interviewer to follow.');
  } else {
    improvements.push('Expand your answer — aim for 60+ words with a clear story.');
  }

  if (/situation|task|action|result|star/i.test(answer) || (/\bI\b/.test(answer) && words >= 40)) {
    score += 25;
    strengths.push('Structured storytelling — interviewers look for clear narrative.');
  } else {
    improvements.push('Use STAR: Situation, Task, Action, Result.');
  }

  if (/team|communicat|collaborat|learn|deliver|result|outcome/i.test(answer)) {
    score += 25;
    strengths.push('Highlights teamwork and outcomes.');
  } else {
    improvements.push('Mention what you did and the measurable outcome.');
  }

  if (!/um|uh|like totally/i.test(answer)) {
    score += 15;
  }

  if (words >= 100) score += 10;

  score = Math.min(100, score);
  const passed = score >= 65;

  return {
    score,
    passed,
    strengths: strengths.length ? strengths : ['You attempted a complete answer.'],
    improvements: improvements.length ? improvements : ['Add one specific metric or result.'],
    sampleOutline:
      'Situation: brief context. Task: your responsibility. Action: what YOU did. Result: outcome with numbers if possible.',
    provider: 'local',
  };
}

function gradeTechnicalLocal(answer: string, type: InterviewQuestionType): InterviewAnswerFeedback {
  const words = wordCount(answer);
  let score = 0;
  const strengths: string[] = [];
  const improvements: string[] = [];

  if (words >= 40) {
    score += 30;
    strengths.push('Sufficient technical depth for a first-pass answer.');
  } else {
    improvements.push('Add more detail — steps, tools, or examples.');
  }

  const techPatterns =
    /test|case|step|sql|api|data|risk|sprint|chart|bug|report|accuracy|stakeholder|group|filter/i;
  if (techPatterns.test(answer)) {
    score += 30;
    strengths.push('Uses domain-relevant terminology.');
  } else {
    improvements.push(`Include ${type === 'technical' ? 'technical' : 'role-specific'} keywords from the question.`);
  }

  if (/\d[\).]|first|then|next|finally|1\.|2\./i.test(answer)) {
    score += 25;
    strengths.push('Organized as steps — easy to follow.');
  } else {
    improvements.push('Number your approach (1, 2, 3) for clarity.');
  }

  if (words >= 80) score += 15;

  score = Math.min(100, score);
  const passed = score >= 65;

  return {
    score,
    passed,
    strengths: strengths.length ? strengths : ['You addressed the question directly.'],
    improvements: improvements.length ? improvements : ['Give a concrete example from practice or simulation.'],
    sampleOutline: 'Definition → your approach → example → how you would verify success.',
    provider: 'local',
  };
}

async function gradeWithOpenAi(input: {
  roleId: SimRole;
  questionType: InterviewQuestionType;
  questionText: string;
  answer: string;
  userContext: string;
}): Promise<InterviewAnswerFeedback> {
  const client = new OpenAI({ apiKey: env.OPENAI_API_KEY! });

  const completion = await client.chat.completions.create({
    model: getMentorModel(),
    messages: [
      {
        role: 'system',
        content: `You are a supportive interview coach. Score mock interview answers 0-100. Be fair to beginners and career returners. Return JSON only: { score, strengths[], improvements[], sampleOutline }. Pass threshold is 65.`,
      },
      {
        role: 'user',
        content: `Role: ${input.roleId}
${input.userContext}

Question (${input.questionType}): ${input.questionText}

Candidate answer:
${input.answer}

Grade this answer. Encourage growth. sampleOutline = 2-3 sentence model answer structure.`,
      },
    ],
    temperature: 0.5,
    max_tokens: 600,
    response_format: { type: 'json_object' },
  });

  const raw = completion.choices[0]?.message?.content ?? '{}';
  const parsed = feedbackSchema.parse(JSON.parse(raw));
  const passed = parsed.score >= 65;

  return { ...parsed, passed, provider: 'openai' };
}

async function buildUserContext(userId: string): Promise<string> {
  const resume = await getLatestAnalysis(userId);
  const job = await getLatestJobMatch(userId);
  const parts: string[] = [];
  if (resume) parts.push(`Candidate skills: ${resume.analysis.skills.slice(0, 8).join(', ')}`);
  if (job) parts.push(`Target job: ${job.jobTitle}`);
  return parts.join('. ') || 'Career transition candidate';
}

export async function gradeInterviewAnswer(input: {
  userId: string;
  roleId: SimRole;
  questionType: InterviewQuestionType;
  questionText: string;
  answer: string;
}): Promise<InterviewAnswerFeedback> {
  if (isMentorConfigured()) {
    try {
      const userContext = await buildUserContext(input.userId);
      return await gradeWithOpenAi({ ...input, userContext });
    } catch {
      /* fall through to local */
    }
  }

  return input.questionType === 'behavioral'
    ? gradeBehavioralLocal(input.answer)
    : gradeTechnicalLocal(input.answer, input.questionType);
}

export function buildImprovementSummary(
  scores: number[],
  improvements: string[],
): string[] {
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
  const summary: string[] = [];

  if (avg < 65) {
    summary.push('Practice structuring answers with STAR for behavioral questions.');
    summary.push('Use numbered steps for technical answers.');
  } else if (avg < 80) {
    summary.push('Solid foundation — add specific metrics and tool names to stand out.');
  } else {
    summary.push('Strong interview performance — keep practicing under time pressure.');
  }

  const unique = [...new Set(improvements)].slice(0, 3);
  return [...summary, ...unique].slice(0, 5);
}

export function isInterviewAiConfigured(): boolean {
  return isMentorConfigured();
}
