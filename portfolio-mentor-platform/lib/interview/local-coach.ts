import type { InterviewRound, InterviewSession, SuggestResponse } from './types';

function roundHint(round: InterviewRound): string {
  switch (round) {
    case 'recruiter':
      return 'Keep it concise, enthusiastic, and aligned with the role level.';
    case 'technical':
      return 'Structure: clarify → approach → example → result. Mention stack from resume.';
    case 'behavioral':
      return 'Use STAR: Situation, Task, Action, Result — 60–90 seconds.';
    default:
      return 'Blend clarity, specifics from your resume, and enthusiasm for the role.';
  }
}

function pickResumeLine(resume: string): string {
  const lines = resume.split(/\n/).map((l) => l.trim()).filter(Boolean);
  return lines.slice(0, 3).join(' ') || 'your recent ML/GenAI project work';
}

export function buildLocalSuggestion(
  session: InterviewSession,
  question: string,
): SuggestResponse {
  const q = question.toLowerCase();
  const snippet = pickResumeLine(session.resume);
  const role = session.roleTitle || 'this role';
  const company = session.company || 'the company';

  let answer: string;
  const bullets: string[] = [];

  if (/tell me about yourself|introduce yourself|walk me through your resume/.test(q)) {
    answer = `I'm a Gen AI / ML engineer with hands-on experience across banking, retail, and insurance. Recently I've built production-style apps including customer segmentation, churn APIs, and RAG systems — ${snippet}. I'm excited about ${role} at ${company} because it matches my strength in shipping ML products end to end.`;
    bullets.push('Present → recent win → why this role', 'Keep under 90 seconds', 'End with why their team');
  } else if (/why (this company|us|here)|why do you want/.test(q)) {
    answer = `I'm drawn to ${company} because the JD emphasizes problems I've solved before — scalable ML, stakeholder-facing delivery, and GenAI where appropriate. My background in ${snippet} maps directly to your needs, and I want to grow impact on a team that values both rigor and shipping.`;
    bullets.push('Tie 2 JD bullets to your resume', 'Show you researched the company', 'Avoid generic praise');
  } else if (/weakness|area of improvement/.test(q)) {
    answer = `Early in my career I sometimes dove into modeling before aligning metrics with business stakeholders. I've improved by defining success criteria upfront — for example on segmentation work I paired silhouette scores with marketing-ready segment narratives. Now I validate the "so what" before optimizing the model.`;
    bullets.push('Real weakness + fix', 'Show growth', 'Avoid cliché perfectionism answers');
  } else if (/salary|compensation|expectations/.test(q)) {
    answer = `I'm flexible based on total compensation and level. Based on the scope in the JD and my experience with production ML/GenAI, I'd like to understand your band for this role first — what range did you budget for ${role}?`;
    bullets.push('Defer with confidence', 'Ask their range first', 'Show flexibility');
  } else if (/system design|architecture|how would you build|design a/.test(q)) {
    answer = `I'd clarify requirements (latency, scale, offline vs online), sketch data flow, then propose a baseline: ingestion → feature store or batch pipeline → model service with FastAPI, monitoring, and rollback. For this JD I'd emphasize ${snippet} and call out trade-offs (batch vs realtime, cost vs accuracy).`;
    bullets.push('Clarify constraints first', 'Draw boxes: data → model → API → UI', 'Mention monitoring & failure modes');
  } else if (/machine learning|ml|model|algorithm|python|rag|llm|genai/.test(q)) {
    answer = `Based on my experience: ${snippet}. For this question I'd explain the problem framing, data, model choice, evaluation metric tied to business outcome, and one lesson learned. Happy to go deeper on implementation or metrics.`;
    bullets.push('Problem → data → model → metric → impact', 'Use a concrete project', 'Offer to whiteboard');
  } else if (/tell me about a time|give an example|describe a situation|conflict|challenge/.test(q)) {
    answer = `Situation: We needed a stakeholder-trusted ML deliverable under tight timelines. Task: I owned end-to-end delivery aligned to the JD skills — ${snippet}. Action: I broke work into milestones, validated each with users, and documented trade-offs. Result: Shipped on schedule with measurable adoption and a reusable playbook for the team.`;
    bullets.push('STAR format', 'Quantify result if possible', 'Under 2 minutes');
  } else {
    answer = `For "${question.slice(0, 80)}${question.length > 80 ? '…' : ''}": connect the JD's core needs to your resume — ${snippet}. Lead with a direct answer, support with one example, and close by linking back to ${role}.`;
    bullets.push(roundHint(session.round), 'Pause, breathe, answer the question asked', 'Ask clarifying question if vague');
  }

  return {
    answer,
    bullets,
    followUpTip: roundHint(session.round),
    source: 'local',
  };
}
