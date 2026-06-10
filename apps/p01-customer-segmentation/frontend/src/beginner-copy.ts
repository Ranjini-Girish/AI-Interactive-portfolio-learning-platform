/** Plain-language labels for non-technical learners */

export const COLUMN_LABELS: Record<string, string> = {
  customer_id: 'Customer ID',
  txn_count: 'Number of transactions',
  avg_balance: 'Average account balance ($)',
  monthly_spend: 'Monthly spending ($)',
};

export function friendlyError(raw: string): string {
  const msg = raw.toLowerCase();
  if (
    msg.includes('not found') ||
    msg.includes('failed to fetch') ||
    msg.includes('could not connect to the data service')
  ) {
    return 'The data service is not running. Double-click START-PORTFOLIO.bat in the portfolio folder, wait ~30 seconds, then refresh this page and try again.';
  }
  if (msg.includes('missing required columns')) {
    return 'Your spreadsheet is missing some required columns. Easiest fix: click "Start with practice data" instead of uploading a file.';
  }
  if (msg.includes('no dataset loaded')) {
    return 'Please load the practice data first (Step 1), then run grouping (Step 2).';
  }
  if (msg.includes('could not parse csv')) {
    return 'We could not read that file. Save it as CSV from Excel (not .xlsx) or use the practice data button.';
  }
  return raw;
}

export const GLOSSARY: { term: string; plain: string }[] = [
  {
    term: 'Customer segment',
    plain: 'A group of customers who behave similarly (similar spending and balances).',
  },
  {
    term: 'Grouping (K-means)',
    plain: 'A math method that sorts customers into groups automatically based on their numbers.',
  },
  {
    term: 'Number of groups',
    plain: 'How many segments you want — try 4 to start. More groups = smaller, more specific buckets.',
  },
  {
    term: 'Practice data',
    plain: 'A ready-made spreadsheet built into this app so you can learn without preparing a file.',
  },
];

export const K_LABELS: Record<number, string> = {
  2: '2 groups — very broad (high vs low spenders)',
  3: '3 groups — simple tiers',
  4: '4 groups — good starting point (recommended)',
  5: '5 groups — more detail',
  6: '6 groups — finer splits',
  7: '7 groups — advanced',
  8: '8 groups — very detailed',
};
