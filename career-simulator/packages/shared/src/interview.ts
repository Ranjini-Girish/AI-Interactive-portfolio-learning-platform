import type { SimRole } from './roles';

export type InterviewQuestionType = 'behavioral' | 'technical';
export type InterviewMode = 'behavioral' | 'technical' | 'mixed';

export type InterviewQuestion = {
  id: string;
  type: InterviewQuestionType;
  text: string;
  tip: string;
};

export type InterviewAnswerFeedback = {
  score: number;
  passed: boolean;
  strengths: string[];
  improvements: string[];
  sampleOutline: string;
  provider: 'openai' | 'local';
};

export type InterviewResponseRecord = {
  questionId: string;
  questionType: InterviewQuestionType;
  questionText: string;
  answerText: string;
  score: number;
  feedback: InterviewAnswerFeedback;
  submittedAt: string;
};

export type InterviewSessionRecord = {
  id: string;
  roleId: SimRole;
  interviewType: InterviewMode;
  status: 'in_progress' | 'completed';
  overallScore: number | null;
  questionsTotal: number;
  questionsAnswered: number;
  improvementSummary: string[];
  createdAt: string;
  completedAt: string | null;
  responses: InterviewResponseRecord[];
  pendingQuestions: InterviewQuestion[];
};

export type InterviewSessionSummary = {
  id: string;
  roleId: SimRole;
  interviewType: InterviewMode;
  status: 'in_progress' | 'completed';
  overallScore: number | null;
  questionsAnswered: number;
  questionsTotal: number;
  createdAt: string;
};

export type InterviewStatusResponse = {
  configured: boolean;
  model: string;
  hasResume: boolean;
};
