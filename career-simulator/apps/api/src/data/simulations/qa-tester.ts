import type { SimModuleDetail } from '@career-sim/shared';

export const QA_SIMULATION: SimModuleDetail = {
  roleId: 'qa_tester',
  label: 'QA Tester',
  company: 'Willamette Valley Digital',
  projectName: 'Mobile Banking Login — Sprint 14',
  description: 'Practice test cases, bug reports, and release triage for a fintech login release.',
  taskCount: 4,
  tasks: [
    {
      id: 'qa-test-cases',
      order: 1,
      kind: 'test_cases',
      title: 'Write test cases for the login page',
      instruction:
        'Write at least two manual test cases for the mobile banking login screen described below. Each test case needs a title, steps, and expected result.',
      scenario: `Product: ValleyPay mobile login (iOS + Android)

Features under test:
• Email + password login
• "Remember me" toggle (30-day session)
• "Forgot password" link sends reset email
• Error message when password is wrong (no hint whether email exists)
• Lock account after 5 failed attempts in 15 minutes

Known build: v2.4.0-rc1 — QA environment https://qa.valleypay.test/login`,
      hints: [
        'Cover one happy path and one negative case (wrong password or empty fields).',
        'Number your steps: 1) Open app 2) Enter email…',
        'Expected result should say what the user sees on screen.',
      ],
      passScore: 70,
    },
    {
      id: 'qa-bug-report',
      order: 2,
      kind: 'bug_report',
      title: 'File a bug report',
      instruction:
        'A tester found an issue: on Android, tapping "Forgot password" twice quickly opens two reset-email modals and the app freezes. Write a professional bug report.',
      scenario: `Environment: Android 14, Pixel 7, ValleyPay v2.4.0-rc1
Steps observed by tester:
1. Open login screen
2. Tap "Forgot password" twice within 1 second
3. Two overlapping modals appear; back button does not dismiss them; app becomes unresponsive

Expected: Only one modal; user can cancel and continue.
Actual: Duplicate modals, UI frozen.`,
      hints: [
        'Pick a severity: Critical / High / Medium / Low.',
        'List clear reproduction steps a developer can follow.',
        'Separate "Expected" vs "Actual" behavior.',
      ],
      passScore: 70,
    },
    {
      id: 'qa-prioritize',
      order: 3,
      kind: 'prioritize',
      title: 'Prioritize defects for release',
      instruction:
        'Release is tomorrow. Drag the defects into priority order (most urgent first). Consider user impact and data/security risk.',
      scenario: `Sprint 14 release candidate — four open defects:

• BUG-401: iOS — "Remember me" ignores toggle; always stays logged in
• BUG-402: Android — Forgot-password double-tap freeze (from previous task)
• BUG-403: Web — Login button text misaligned on Safari (cosmetic)
• BUG-402: API — Wrong-password message shows HTTP 500 in logs (no user impact)`,
      hints: [
        'Security/session bugs often outrank cosmetic issues.',
        'Crash or freeze on a common flow is usually High or Critical.',
      ],
      passScore: 75,
    },
    {
      id: 'qa-regression',
      order: 4,
      kind: 'written',
      title: 'Explain regression vs smoke testing',
      instruction:
        'In 4–8 sentences, explain the difference between smoke testing and regression testing. Use the ValleyPay login release as an example.',
      scenario: `Your team asks you to explain testing types in tomorrow's standup. Keep it simple — assume the PM is non-technical.`,
      hints: [
        'Smoke = quick "is the build testable?" checks on main flows.',
        'Regression = re-running tests to ensure old features still work after changes.',
      ],
      passScore: 65,
    },
  ],
};

/** Canonical defect priority for qa-prioritize (bug ids) */
export const QA_DEFECT_IDS = ['bug-402-freeze', 'bug-401-remember', 'bug-500-logs', 'bug-403-cosmetic'];

export const QA_DEFECTS = [
  { id: 'bug-402-freeze', label: 'BUG-402: Android forgot-password double-tap freeze' },
  { id: 'bug-401-remember', label: 'BUG-401: iOS "Remember me" always on' },
  { id: 'bug-500-logs', label: 'BUG-404: API 500 in logs on wrong password' },
  { id: 'bug-403-cosmetic', label: 'BUG-403: Safari login button alignment' },
];
