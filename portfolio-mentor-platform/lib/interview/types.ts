export type InterviewRound = 'recruiter' | 'technical' | 'behavioral' | 'mixed';

export type InterviewSession = {
  jobDescription: string;
  resume: string;
  round: InterviewRound;
  company?: string;
  roleTitle?: string;
};

export type SuggestRequest = {
  session: InterviewSession;
  question: string;
  transcriptTail?: string;
  userApiKey?: string;
};

export type SuggestResponse = {
  answer: string;
  bullets: string[];
  followUpTip: string;
  source: 'openai' | 'local';
};

export const STORAGE_KEY = 'interview-copilot-session-v1';
export const OVERLAY_CHANNEL = 'interview-copilot-sync';

export type OverlayMessage =
  | { type: 'state'; question: string; answer: string; bullets: string[]; listening: boolean }
  | { type: 'ping' };
