import type {
  SimRole,
  SimTaskProgress,
  SimTaskSubmitPayload,
  SimTaskSubmitResult,
  SimulationSessionRecord,
} from '@career-sim/shared';
import { QA_DEFECT_IDS } from '../data/simulations/qa-tester';
import { getTaskDefinition } from '../data/simulations';

function clamp(n: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, n));
}

function wordCount(text: string) {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function countMatches(text: string, patterns: RegExp[]) {
  return patterns.filter((p) => p.test(text)).length;
}

function gradeTestCases(text: string): SimTaskSubmitResult {
  const feedback: string[] = [];
  let score = 0;

  const cases = text.split(/(?:test case|tc[- ]?\d+|case \d+)/i).filter((s) => s.trim().length > 30);
  const caseCount = Math.max(cases.length, (text.match(/test case/gi) ?? []).length);

  if (caseCount >= 2 || wordCount(text) >= 80) {
    score += 30;
    feedback.push('Good — you documented multiple test scenarios.');
  } else {
    feedback.push('Add at least two distinct test cases with clear titles.');
  }

  if (/step|given|when|then|\d[\).]/i.test(text)) {
    score += 25;
    feedback.push('Steps are structured — easy for another tester to follow.');
  } else {
    feedback.push('Number your steps (1, 2, 3) or use Given/When/Then.');
  }

  if (/expect|should|result|see|display/i.test(text)) {
    score += 25;
    feedback.push('Expected results are included.');
  } else {
    feedback.push('State the expected result for each case.');
  }

  if (/password|login|email|remember|forgot/i.test(text)) {
    score += 20;
    feedback.push('Cases relate to the login feature under test.');
  } else {
    feedback.push('Tie cases to the login screen requirements.');
  }

  score = clamp(score);
  const passed = score >= 70;
  if (passed) feedback.unshift('Passed — solid manual test case writing.');
  return { score, passed, feedback, status: passed ? 'passed' : 'needs_revision' };
}

function gradeBugReport(payload: Extract<SimTaskSubmitPayload, { kind: 'bug_report' }>): SimTaskSubmitResult {
  const feedback: string[] = [];
  let score = 0;
  const { title, severity, steps, expected, actual } = payload;

  if (title.trim().length >= 8) {
    score += 15;
  } else {
    feedback.push('Add a clear, specific bug title.');
  }

  if (/critical|high|medium|low|sev/i.test(severity)) {
    score += 20;
    feedback.push('Severity is documented.');
  } else {
    feedback.push('Pick a severity level (Critical / High / Medium / Low).');
  }

  if (wordCount(steps) >= 15 || /\d[\).]/m.test(steps)) {
    score += 25;
    feedback.push('Reproduction steps are detailed.');
  } else {
    feedback.push('Expand reproduction steps so a developer can replay the bug.');
  }

  if (expected.trim().length >= 10) score += 20;
  else feedback.push('Describe expected behavior.');

  if (actual.trim().length >= 10) score += 20;
  else feedback.push('Describe actual behavior.');

  score = clamp(score);
  const passed = score >= 70;
  if (passed) feedback.unshift('Passed — this is a professional bug report.');
  return { score, passed, feedback, status: passed ? 'passed' : 'needs_revision' };
}

function gradePrioritize(order: string[]): SimTaskSubmitResult {
  const feedback: string[] = [];
  const canonical = QA_DEFECT_IDS;
  let matches = 0;
  for (let i = 0; i < Math.min(order.length, canonical.length); i++) {
    if (order[i] === canonical[i]) matches++;
  }
  const score = clamp(Math.round((matches / canonical.length) * 100));
  if (order[0] === 'bug-402-freeze') {
    feedback.push('Correct — freeze on a core flow is top priority.');
  } else {
    feedback.push('The Android freeze should usually be fixed before cosmetic issues.');
  }
  if (order.includes('bug-403-cosmetic') && order.indexOf('bug-403-cosmetic') >= 2) {
    feedback.push('Cosmetic issues typically rank lower than functional bugs.');
  }
  const passed = score >= 75;
  if (passed) feedback.unshift('Passed — sensible release triage order.');
  else feedback.push('Reorder: security/session → crashes → logs → cosmetic.');
  return { score, passed, feedback, status: passed ? 'passed' : 'needs_revision' };
}

function gradeWritten(text: string, taskId: string): SimTaskSubmitResult {
  const feedback: string[] = [];
  let score = 0;
  const words = wordCount(text);

  if (words >= 40) {
    score += 25;
  } else {
    feedback.push('Write a bit more — aim for at least 4–5 sentences.');
  }

  if (taskId === 'qa-regression') {
    if (/smoke/i.test(text)) score += 25;
    else feedback.push('Define smoke testing.');
    if (/regression/i.test(text)) score += 25;
    else feedback.push('Define regression testing.');
    if (/login|valley|release|example/i.test(text)) score += 25;
    else feedback.push('Use the ValleyPay login release as an example.');
  }

  if (taskId.startsWith('da-')) {
    const numHits = countMatches(text, [/\d{2,}/, /west|east/i, /care plus|wellness/i, /revenue|units/i]);
    score += Math.min(40, numHits * 12);
    if (numHits >= 2) feedback.push('Insights are backed by data — good analyst habit.');
    else feedback.push('Reference specific numbers, regions, or products from the dataset.');
    if (taskId === 'da-summary' && /recommend|next step|suggest/i.test(text)) score += 15;
    if (taskId === 'da-sql-thought' && /group|sum|filter|march|region/i.test(text)) score += 20;
  }

  if (taskId.startsWith('pm-')) {
    if (taskId === 'pm-plan' && /milestone|week|phase|deliver/i.test(text)) score += 35;
    if (taskId === 'pm-risks' && /risk|mitig|impact|likelihood/i.test(text)) score += 35;
    if (taskId === 'pm-sprint' && /story|sprint goal|as a|implement|qa|test/i.test(text)) score += 35;
    if (taskId === 'pm-status' && /green|amber|red|blocker|progress/i.test(text)) score += 35;
    if (/(risk|milestone|story|status)/i.test(text)) {
      feedback.push('Covers key PM concepts.');
    }
  }

  if (taskId.startsWith('ar-')) {
    if (taskId === 'ar-rubric' && /accur|tone|safe|complete/i.test(text)) score += 35;
    if (taskId === 'ar-feedback' && /hallucin|wrong|incorrect|fix|unsafe/i.test(text)) score += 35;
    if (taskId === 'ar-policy' && /check|verify|escalat|fact|pii/i.test(text)) score += 35;
  }

  if (words >= 60) score += 15;

  score = clamp(score);
  const passScore = taskId === 'da-sql-thought' ? 60 : 65;
  const passed = score >= passScore;
  if (passed) feedback.unshift('Passed — clear and relevant response.');
  return { score, passed, feedback, status: passed ? 'passed' : 'needs_revision' };
}

function gradeReview(payload: Extract<SimTaskSubmitPayload, { kind: 'review' }>): SimTaskSubmitResult {
  const feedback: string[] = [];
  let score = 0;
  const { ratings, feedback: userFeedback } = payload;

  const bRating = ratings['sample-b'];
  if (bRating !== undefined && bRating <= 2) {
    score += 40;
    feedback.push('You correctly rated the IRS/8899-B answer as low accuracy.');
  } else {
    feedback.push('Sample B is a hallucination — accuracy should be 1 or 2.');
  }

  const aRating = ratings['sample-a'];
  const cRating = ratings['sample-c'];
  if (aRating !== undefined && aRating >= 3) score += 20;
  if (cRating !== undefined && cRating >= 3) score += 20;

  if (/hallucin|fabricat|false|8899|irs|unsafe/i.test(userFeedback)) {
    score += 20;
    feedback.push('Feedback identifies the core quality issue.');
  } else {
    feedback.push('Mention why Sample B is unsafe or fabricated.');
  }

  score = clamp(score);
  const passed = score >= 75;
  if (passed) feedback.unshift('Passed — strong reviewer judgment.');
  return { score, passed, feedback, status: passed ? 'passed' : 'needs_revision' };
}

export function gradeTaskSubmission(
  roleId: SimRole,
  taskId: string,
  payload: SimTaskSubmitPayload,
): SimTaskSubmitResult {
  const task = getTaskDefinition(roleId, taskId);
  if (!task) {
    return { score: 0, passed: false, feedback: ['Unknown task'], status: 'needs_revision' };
  }

  let result: SimTaskSubmitResult;
  switch (payload.kind) {
    case 'test_cases':
      result = gradeTestCases(payload.text);
      break;
    case 'bug_report':
      result = gradeBugReport(payload);
      break;
    case 'prioritize':
      result = gradePrioritize(payload.order);
      break;
    case 'review':
      result = gradeReview(payload);
      break;
    case 'written':
    default:
      result = gradeWritten(payload.text, taskId);
      break;
  }

  if (result.score < task.passScore) {
    result.passed = false;
    result.status = 'needs_revision';
  }

  return result;
}
