import type { SimModuleDetail, SimModuleMeta, SimRole } from '@career-sim/shared';
import { QA_SIMULATION, QA_DEFECTS } from './qa-tester';
import { DATA_ANALYST_SIMULATION, DATA_ANALYST_DATASET } from './data-analyst';
import { PM_SIMULATION } from './project-manager';
import { AI_REVIEWER_SIMULATION, AI_REVIEW_SAMPLES } from './ai-reviewer';

const MODULES: SimModuleDetail[] = [
  QA_SIMULATION,
  DATA_ANALYST_SIMULATION,
  PM_SIMULATION,
  AI_REVIEWER_SIMULATION,
];

const byRole = new Map<SimRole, SimModuleDetail>(MODULES.map((m) => [m.roleId, m]));

export function listSimulationModules(): SimModuleMeta[] {
  return MODULES.map(({ tasks, ...meta }) => meta);
}

export function getSimulationModule(roleId: SimRole): SimModuleDetail | null {
  return byRole.get(roleId) ?? null;
}

export function getTaskDefinition(roleId: SimRole, taskId: string) {
  const mod = byRole.get(roleId);
  return mod?.tasks.find((t) => t.id === taskId) ?? null;
}

export function getSimulationFixtures(roleId: SimRole, taskId: string) {
  if (roleId === 'qa_tester' && taskId === 'qa-prioritize') {
    return { defects: QA_DEFECTS };
  }
  if (roleId === 'data_analyst' && taskId === 'da-explore') {
    return { dataset: DATA_ANALYST_DATASET };
  }
  if (roleId === 'ai_reviewer' && taskId === 'ar-rate') {
    return { samples: AI_REVIEW_SAMPLES };
  }
  return {};
}

export { QA_DEFECTS, DATA_ANALYST_DATASET, AI_REVIEW_SAMPLES };
