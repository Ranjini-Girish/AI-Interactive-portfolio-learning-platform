import OpenAI from 'openai';
import type { MentorMessage } from '@career-sim/shared';
import { env } from '../config/env';
import {
  buildMentorContextBlock,
  getMentorModel,
  isMentorConfigured,
  MENTOR_SYSTEM_PROMPT,
} from './mentor-prompt';

function getClient(): OpenAI {
  if (!env.OPENAI_API_KEY) throw new Error('OPENAI_API_KEY not configured');
  return new OpenAI({ apiKey: env.OPENAI_API_KEY });
}

export async function streamMentorReply(
  userId: string,
  userMessage: string,
  history: MentorMessage[],
  onToken: (chunk: string) => void,
): Promise<string> {
  const client = getClient();
  const context = await buildMentorContextBlock(userId);

  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: 'system', content: `${MENTOR_SYSTEM_PROMPT}\n\n${context}` },
    ...history.map((m) => ({
      role: m.role as 'user' | 'assistant',
      content: m.content,
    })),
    { role: 'user', content: userMessage },
  ];

  const stream = await client.chat.completions.create({
    model: getMentorModel(),
    messages,
    stream: true,
    temperature: 0.7,
    max_tokens: 900,
  });

  let full = '';
  for await (const chunk of stream) {
    const text = chunk.choices[0]?.delta?.content ?? '';
    if (text) {
      full += text;
      onToken(text);
    }
  }
  return full;
}

/** Offline fallback when OpenAI key is missing — still helpful for demos */
export function localMentorReply(userMessage: string, hasContext: boolean): string {
  const q = userMessage.toLowerCase();
  if (q.includes('api')) {
    return `Great question! An **API** is like a **waiter in a restaurant**.

1. **Simple definition:** It's a way for one program to ask another program for data or action — without needing to know how the kitchen works inside.
2. **Real example:** When a banking app shows your balance, it often calls the bank's API to fetch that number securely.
3. **For QA testers:** You use tools like Postman to send test requests to an API and check the response — like ordering "check password reset" and verifying the kitchen sends back the right dish.

**Try this next:** Open our Job Match or Resume lab and note any "API testing" skill — practice one Postman GET request on a public sample API.`;
  }
  if (q.includes('roadmap') || q.includes('first') || q.includes('start')) {
    return hasContext
      ? `You're on the right track! Based on your saved resume and job match:

1. Pick **one skill gap** from your match report — don't try to learn everything at once.
2. Spend **30 minutes today** on a hands-on micro-task (e.g., write 3 test cases or run one SQL query).
3. Come back and tell me what you did — I'll review it like a teammate would.

**Try this next:** Tell me which gap confuses you most, and I'll break it into smaller steps.`
      : `Welcome! Here's your first-week path:

1. **Upload or try a sample resume** at /resume — we extract your skills automatically.
2. **Match a job posting** at /job — see gaps before you apply.
3. Ask me to explain anything that sounds intimidating.

**Try this next:** Analyze the "QA career returner" sample resume, then ask me about your results.`;
  }
  return `I'm your work mentor — I explain things in plain English with examples.

To give you personalized steps, **upload a resume** and **match a job** first (Phases 3–4). Then ask me things like:
• "What is an API?"
• "What should I learn first from my gaps?"
• "Help me practice for a QA interview"

**Try this next:** Ask about any term on your job match report that feels unclear.`;
}

export { isMentorConfigured, getMentorModel };
