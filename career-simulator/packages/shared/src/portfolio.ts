import type { SimRole } from './roles';

export type PortfolioProject = {
  title: string;
  role: SimRole;
  company: string;
  summary: string;
  bullets: string[];
  skillsDemonstrated: string[];
};

export type PortfolioContent = {
  headline: string;
  targetRole: string;
  resumeBullets: string[];
  linkedInHeadline: string;
  linkedInAbout: string;
  projects: PortfolioProject[];
  githubReadme: string;
  provider: 'openai' | 'local';
  generatedAt: string;
};

export type PortfolioRecord = {
  id: string;
  content: PortfolioContent;
  createdAt: string;
};

export type PortfolioStatusResponse = {
  configured: boolean;
  model: string;
  hasResume: boolean;
  hasGeneration: boolean;
};
