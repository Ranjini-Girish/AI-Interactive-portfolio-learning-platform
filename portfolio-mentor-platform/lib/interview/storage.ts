import type { InterviewSession } from './types';
import { STORAGE_KEY } from './types';

const defaultSession: InterviewSession = {
  jobDescription: '',
  resume: '',
  round: 'mixed',
  company: '',
  roleTitle: '',
};

export function loadSession(): InterviewSession {
  if (typeof window === 'undefined') return defaultSession;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultSession;
    return { ...defaultSession, ...JSON.parse(raw) };
  } catch {
    return defaultSession;
  }
}

export function saveSession(session: InterviewSession): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function loadUserApiKey(): string {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('interview-copilot-openai-key') ?? '';
}

export function saveUserApiKey(key: string): void {
  if (typeof window === 'undefined') return;
  if (key) localStorage.setItem('interview-copilot-openai-key', key);
  else localStorage.removeItem('interview-copilot-openai-key');
}
