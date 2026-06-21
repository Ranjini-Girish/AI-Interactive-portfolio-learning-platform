export type MentorMessage = {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt?: string;
};

export type MentorChatRequest = {
  message: string;
  clearHistory?: boolean;
};

export type MentorStatusResponse = {
  configured: boolean;
  model: string;
  message: string;
};

export type MentorHistoryResponse = {
  messages: MentorMessage[];
};

export const MENTOR_STARTER_PROMPTS = [
  'What is an API? Explain like I am new to tech.',
  'What should I do first on my learning roadmap?',
  'Help me understand the skill gaps from my job match.',
  'How do I explain my career gap in an interview?',
];
