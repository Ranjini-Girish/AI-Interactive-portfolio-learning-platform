import type {
  AuthResponse,
  HealthResponse,
  LoginRequest,
  MeResponse,
  RegisterRequest,
  ResumeAnalysisRecord,
  ResumeSampleMeta,
  JobMatchRecord,
  JobSampleMeta,
  SimRole,
} from '@career-sim/shared';
import type { ProgressDashboard } from '@career-sim/shared';
import { getAuthToken } from './auth-token';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:4000';

export type ApiClientError = {
  error: string;
  code?: string;
};

async function apiFetch<T>(
  path: string,
  options: RequestInit & { auth?: boolean; json?: boolean } = {},
): Promise<T> {
  const useJson = options.json !== false;
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (useJson && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  if (options.auth !== false) {
    const token = await getAuthToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw data as ApiClientError;
  }
  return data as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/api/health', { auth: false, cache: 'no-store' as RequestCache });
}

export async function registerUser(body: RegisterRequest): Promise<AuthResponse> {
  return apiFetch<AuthResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(body),
    auth: false,
  });
}

export async function loginUser(body: LoginRequest): Promise<AuthResponse> {
  return apiFetch<AuthResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(body),
    auth: false,
  });
}

export async function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>('/api/auth/me');
}

export type DashboardResponse = {
  message: string;
  phase: number;
  nextStep: string;
  stats: {
    tasksCompleted: number;
    skillsLearned: number;
    jobReadinessScore: number;
    projectsInProgress: number;
  };
  resume: {
    id: string;
    headline: string;
    topRole: string | null;
    topScore: number | null;
  } | null;
  jobMatch: {
    id: string;
    jobTitle: string;
    matchScore: number;
    gapCount: number;
  } | null;
  simulation: {
    roleId: string;
    progressPercent: number;
    tasksCompleted: number;
    totalTasks: number;
  } | null;
};

export async function fetchProgressDashboard(): Promise<ProgressDashboard> {
  return apiFetch<ProgressDashboard>('/api/progress/dashboard');
}

/** @deprecated Use fetchProgressDashboard — kept for backward compatibility */
export async function fetchDashboard(): Promise<DashboardResponse> {
  return apiFetch<DashboardResponse>('/api/auth/dashboard');
}

export async function fetchResumeSamples(): Promise<{ samples: ResumeSampleMeta[] }> {
  return apiFetch('/api/resume/samples', { auth: false });
}

export async function analyzeResumeText(
  text: string,
  targetRole?: SimRole,
): Promise<ResumeAnalysisRecord> {
  return apiFetch('/api/resume/analyze-text', {
    method: 'POST',
    body: JSON.stringify({ text, targetRole }),
  });
}

export async function analyzeResumeSample(
  sampleId: string,
  targetRole?: SimRole,
): Promise<ResumeAnalysisRecord> {
  return apiFetch('/api/resume/analyze-sample', {
    method: 'POST',
    body: JSON.stringify({ sampleId, targetRole }),
  });
}

export async function uploadResumeFile(
  file: File,
  targetRole?: SimRole,
): Promise<ResumeAnalysisRecord> {
  const token = await getAuthToken();
  const form = new FormData();
  form.append('file', file);
  if (targetRole) form.append('targetRole', targetRole);

  const res = await fetch(`${API_URL}/api/resume/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw data as ApiClientError;
  return data as ResumeAnalysisRecord;
}

export async function fetchLatestResume(): Promise<ResumeAnalysisRecord> {
  return apiFetch('/api/resume/latest');
}

export async function fetchJobSamples(): Promise<{ samples: JobSampleMeta[] }> {
  return apiFetch('/api/job/samples', { auth: false });
}

export async function matchJobText(jdText: string, targetRole?: SimRole): Promise<JobMatchRecord> {
  return apiFetch('/api/job/match', {
    method: 'POST',
    body: JSON.stringify({ jdText, targetRole }),
  });
}

export async function matchJobSample(
  sampleId: string,
  targetRole?: SimRole,
): Promise<JobMatchRecord> {
  return apiFetch('/api/job/match-sample', {
    method: 'POST',
    body: JSON.stringify({ sampleId, targetRole }),
  });
}

export async function fetchLatestJobMatch(): Promise<JobMatchRecord> {
  return apiFetch('/api/job/latest');
}

export async function fetchMentorStatus(): Promise<import('@career-sim/shared').MentorStatusResponse> {
  return apiFetch('/api/mentor/status');
}

export async function fetchMentorHistory(): Promise<import('@career-sim/shared').MentorHistoryResponse> {
  return apiFetch('/api/mentor/history');
}

export async function clearMentorHistory(): Promise<{ ok: boolean }> {
  return apiFetch('/api/mentor/history', { method: 'DELETE', json: false });
}

export async function fetchSimulationModules(): Promise<{
  modules: import('@career-sim/shared').SimModuleOverview[];
}> {
  return apiFetch('/api/simulation/modules');
}

export async function fetchSimulationModule(roleId: SimRole): Promise<{
  module: import('@career-sim/shared').SimModuleDetail;
}> {
  return apiFetch(`/api/simulation/modules/${roleId}`);
}

export async function startSimulationSession(roleId: SimRole): Promise<{
  session: import('@career-sim/shared').SimulationSessionRecord;
}> {
  return apiFetch(`/api/simulation/sessions/${roleId}/start`, { method: 'POST' });
}

export async function fetchSimulationSession(roleId: SimRole): Promise<{
  session: import('@career-sim/shared').SimulationSessionRecord;
}> {
  return apiFetch(`/api/simulation/sessions/${roleId}`);
}

export async function fetchSimulationTaskFixtures(
  roleId: SimRole,
  taskId: string,
): Promise<{ task: import('@career-sim/shared').SimTaskDefinition; fixtures: Record<string, unknown> }> {
  return apiFetch(`/api/simulation/tasks/${roleId}/${taskId}/fixtures`);
}

export async function submitSimulationTask(
  roleId: SimRole,
  taskId: string,
  payload: import('@career-sim/shared').SimTaskSubmitPayload,
): Promise<{
  grade: import('@career-sim/shared').SimTaskSubmitResult;
  session: import('@career-sim/shared').SimulationSessionRecord;
}> {
  return apiFetch(`/api/simulation/tasks/${roleId}/${taskId}/submit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function generatePortfolioContent(): Promise<import('@career-sim/shared').PortfolioRecord> {
  return apiFetch('/api/portfolio/generate', { method: 'POST' });
}

export async function fetchLatestPortfolio(): Promise<import('@career-sim/shared').PortfolioRecord> {
  return apiFetch('/api/portfolio/latest');
}

export async function fetchPortfolioStatus(): Promise<import('@career-sim/shared').PortfolioStatusResponse> {
  return apiFetch('/api/portfolio/status');
}

export async function fetchInterviewStatus(): Promise<import('@career-sim/shared').InterviewStatusResponse> {
  return apiFetch('/api/interview/status');
}

export async function fetchInterviewSessions(): Promise<{
  sessions: import('@career-sim/shared').InterviewSessionSummary[];
}> {
  return apiFetch('/api/interview/sessions');
}

export async function startInterviewSession(
  roleId: SimRole,
  interviewType: import('@career-sim/shared').InterviewMode,
): Promise<{ session: import('@career-sim/shared').InterviewSessionRecord }> {
  return apiFetch('/api/interview/sessions', {
    method: 'POST',
    body: JSON.stringify({ roleId, interviewType }),
  });
}

export async function fetchInterviewSession(sessionId: string): Promise<{
  session: import('@career-sim/shared').InterviewSessionRecord;
}> {
  return apiFetch(`/api/interview/sessions/${sessionId}`);
}

export async function submitInterviewAnswer(
  sessionId: string,
  questionId: string,
  answer: string,
): Promise<{
  feedback: import('@career-sim/shared').InterviewAnswerFeedback;
  session: import('@career-sim/shared').InterviewSessionRecord;
}> {
  return apiFetch(`/api/interview/sessions/${sessionId}/answer`, {
    method: 'POST',
    body: JSON.stringify({ questionId, answer }),
  });
}

export { API_URL };
