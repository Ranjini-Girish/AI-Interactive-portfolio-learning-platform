import { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  checkHealth,
  loadSampleDataset,
  runSegmentation,
  summarizeSegments,
  saveLabProof,
  uploadCsv,
  type SegmentResult,
  type StakeholderSummary,
  type UploadSummary,
} from './api';
import {
  COLUMN_LABELS,
  friendlyError,
  GLOSSARY,
  K_LABELS,
} from './beginner-copy';

const COLORS = ['#2563eb', '#7c3aed', '#059669', '#db2777', '#d97706', '#dc2626', '#0891b2', '#4f46e5'];
const WELCOME_KEY = 'p01-beginner-welcome-v1';

function StepCard({
  n,
  title,
  subtitle,
  done,
  active,
  children,
}: {
  n: number;
  title: string;
  subtitle: string;
  done: boolean;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className={`card ${active ? 'active-step' : ''} ${done ? 'done-step' : ''}`}>
      <div className="step-header">
        <div className={`step-num ${done ? 'done' : ''}`}>{done ? '✓' : n}</div>
        <div>
          <h2 className="step-title">{title}</h2>
          <p className="step-subtitle">{subtitle}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

export default function App() {
  const [showWelcome, setShowWelcome] = useState(false);
  const [summary, setSummary] = useState<UploadSummary | null>(null);
  const [segments, setSegments] = useState<SegmentResult | null>(null);
  const [k, setK] = useState(4);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const [stakeholderSummary, setStakeholderSummary] = useState<StakeholderSummary | null>(null);
  const [summarizeLoading, setSummarizeLoading] = useState(false);
  const [summarizeError, setSummarizeError] = useState('');
  const [proofUrl, setProofUrl] = useState('');
  const [proofLoading, setProofLoading] = useState(false);
  const [proofError, setProofError] = useState('');

  const step1Done = !!summary;
  const step2Done = !!segments;
  const step4Done = !!stakeholderSummary;
  const currentStep = !step1Done ? 1 : !step2Done ? 2 : !step4Done ? 3 : 4;

  useEffect(() => {
    if (!localStorage.getItem(WELCOME_KEY)) {
      setShowWelcome(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function ping() {
      const ok = await checkHealth();
      if (!cancelled) setServiceOnline(ok);
    }
    void ping();
    const id = window.setInterval(() => void ping(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  function dismissWelcome(startSample: boolean) {
    localStorage.setItem(WELCOME_KEY, '1');
    setShowWelcome(false);
    if (startSample) void handleLoadSample();
  }

  async function handleLoadSample() {
    setError('');
    setLoading(true);
    setSegments(null);
    setStakeholderSummary(null);
    try {
      const result = await loadSampleDataset();
      setSummary(result);
    } catch (err) {
      setSummary(null);
      setError(friendlyError(err instanceof Error ? err.message : 'Could not load practice data'));
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(file: File | null) {
    if (!file) return;
    setError('');
    setLoading(true);
    setSegments(null);
    setStakeholderSummary(null);
    try {
      const result = await uploadCsv(file);
      setSummary(result);
    } catch (err) {
      setSummary(null);
      setError(friendlyError(err instanceof Error ? err.message : 'Upload failed'));
    } finally {
      setLoading(false);
    }
  }

  async function handleSegment() {
    setError('');
    setStakeholderSummary(null);
    setSummarizeError('');
    setLoading(true);
    try {
      const result = await runSegmentation(k);
      setSegments(result);
    } catch (err) {
      setError(friendlyError(err instanceof Error ? err.message : 'Grouping failed'));
    } finally {
      setLoading(false);
    }
  }

  async function handleSummarize() {
    if (!segments) return;
    setSummarizeError('');
    setSummarizeLoading(true);
    try {
      const result = await summarizeSegments(segments);
      setStakeholderSummary(result);
    } catch (err) {
      setStakeholderSummary(null);
      setSummarizeError(friendlyError(err instanceof Error ? err.message : 'Summary failed'));
    } finally {
      setSummarizeLoading(false);
    }
  }

  async function copySummary() {
    if (!stakeholderSummary) return;
    const text = [
      stakeholderSummary.summary,
      '',
      ...stakeholderSummary.bullets.map((b) => `• ${b}`),
      '',
      stakeholderSummary.model
        ? `Model: ${stakeholderSummary.model} (${stakeholderSummary.provider})`
        : `Provider: ${stakeholderSummary.provider} (no HF token — rule-based fallback)`,
    ].join('\n');
    await navigator.clipboard.writeText(text);
  }

  async function handleSaveProof() {
    if (!stakeholderSummary || !segments) return;
    setProofError('');
    setProofLoading(true);
    try {
      const result = await saveLabProof({
        lab_slug: 'customer-segmentation-lab',
        title: 'Customer Segmentation Lab — Willamette Valley Bank',
        summary: stakeholderSummary.summary,
        bullets: stakeholderSummary.bullets,
        metrics: {
          k: segments.metrics.k,
          silhouette_score: segments.metrics.silhouette_score.toFixed(3),
          inertia: Math.round(segments.metrics.inertia),
        },
        provider: stakeholderSummary.provider,
        model: stakeholderSummary.model,
      });
      setProofUrl(result.proof_url);
    } catch (err) {
      setProofUrl('');
      setProofError(friendlyError(err instanceof Error ? err.message : 'Save failed'));
    } finally {
      setProofLoading(false);
    }
  }

  const scatterGroups = useMemo(() => {
    if (!segments) return [];
    const bySegment = new Map<number, typeof segments.customers>();
    for (const c of segments.customers) {
      const list = bySegment.get(c.segment_id) ?? [];
      list.push(c);
      bySegment.set(c.segment_id, list);
    }
    return [...bySegment.entries()].map(([segmentId, customers]) => ({
      segmentId,
      name: customers[0]?.segment_name ?? `Group ${segmentId + 1}`,
      customers,
    }));
  }, [segments]);

  const topPerSegment = useMemo(() => {
    if (!segments) return [];
    const groups = new Map<number, typeof segments.customers>();
    for (const c of segments.customers) {
      const list = groups.get(c.segment_id) ?? [];
      list.push(c);
      groups.set(c.segment_id, list);
    }
    return [...groups.entries()].map(([id, customers]) => ({
      segment_id: id,
      segment_name: customers[0]?.segment_name ?? `Group ${id + 1}`,
      top: [...customers].sort((a, b) => b.monthly_spend - a.monthly_spend).slice(0, 5),
    }));
  }, [segments]);

  return (
    <div className="app-shell">
      {showWelcome && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="welcome-title">
          <div className="modal">
            <h2 id="welcome-title">Welcome — learn step by step</h2>
            <p>
              No coding or spreadsheet prep needed. We&apos;ll use <strong>practice bank data</strong>{' '}
              and show you how banks group customers by spending habits.
            </p>
            <ol>
              <li>Load practice data (one click)</li>
              <li>Choose how many groups you want</li>
              <li>See the chart and customer lists</li>
            </ol>
            <button type="button" className="big" onClick={() => dismissWelcome(true)}>
              Start with practice data
            </button>
            <button
              type="button"
              className="ghost big"
              style={{ marginTop: '0.5rem' }}
              onClick={() => dismissWelcome(false)}
            >
              I&apos;ll explore on my own
            </button>
          </div>
        </div>
      )}

      {serviceOnline === false && (
        <div className="offline-banner" role="alert">
          <strong>Data service offline.</strong> Run{' '}
          <code>portfolio-mentor-platform/START-PORTFOLIO.bat</code>, wait until it says
          &quot;P01 Seg&quot; is ready, then refresh this page.
        </div>
      )}

      <header className="hero">
        <span className="hero-badge">Beginner-friendly lab · No experience needed</span>
        <h1>Customer Grouping Lab</h1>
        <p className="hero-sub">
          Learn how banks sort customers into groups based on spending and account balance —
          using real machine-learning ideas, explained in plain English.
        </p>
      </header>

      <div className="progress-track" aria-label="Your progress">
        {[1, 2, 3, 4].map((s) => (
          <div
            key={s}
            className={`progress-seg ${s < currentStep || (step4Done && s <= 3) ? 'done' : ''} ${s === currentStep ? 'active' : ''}`}
          />
        ))}
      </div>
      <div className="progress-labels progress-labels-4">
        <span>Load data</span>
        <span>Group customers</span>
        <span>Explore results</span>
        <span>Lab report</span>
      </div>

      <StepCard
        n={1}
        title="Load your data"
        subtitle="Start with our built-in practice file — no download required."
        done={step1Done}
        active={currentStep === 1}
      >
        <div className="tip-box">
          <strong>New here?</strong> Click the blue button below. It loads 80 sample customers
          instantly — the same data your instructor uses for demos.
        </div>

        <button type="button" className="big" disabled={loading} onClick={handleLoadSample}>
          {loading && !summary ? 'Loading practice data…' : 'Start with practice data (recommended)'}
        </button>

        <div className="upload-zone">
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.9rem' }}>
            Already have a spreadsheet?
          </p>
          <label>
            Choose a CSV file from your computer
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={loading}
              onChange={(e) => handleUpload(e.target.files?.[0] ?? null)}
            />
          </label>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem', color: 'var(--muted)' }}>
            Tip: In Excel, use <strong>Save As → CSV</strong>. Column names like &quot;Customer
            ID&quot; work automatically.
          </p>
        </div>

        {error && currentStep === 1 && <div className="tip-box error">{error}</div>}

        {summary && (
          <div className="tip-box success">
            <strong>Step 1 complete!</strong> {summary.row_count} customers loaded. Scroll down to
            Step 2.
          </div>
        )}

        {summary && (
          <div className="stats-grid">
            {Object.entries(summary.stats).map(([col, s]) => (
              <div key={col} className="stat-row">
                <span>{COLUMN_LABELS[col] ?? col}</span>
                <span>
                  ${s.min.toLocaleString()} – ${s.max.toLocaleString()} (avg ${s.mean.toLocaleString()})
                </span>
              </div>
            ))}
          </div>
        )}
      </StepCard>

      <StepCard
        n={2}
        title="Group similar customers"
        subtitle="The app finds patterns and splits customers into groups."
        done={step2Done}
        active={currentStep === 2}
      >
        {!step1Done ? (
          <div className="tip-box warning">Complete Step 1 first — load the practice data.</div>
        ) : (
          <>
            <div className="slider-block">
              <label htmlFor="group-count">How many groups? ({k})</label>
              <input
                id="group-count"
                type="range"
                min={2}
                max={8}
                value={k}
                disabled={loading}
                onChange={(e) => setK(Number(e.target.value))}
              />
              <p className="slider-hint">{K_LABELS[k] ?? `${k} groups`}</p>
            </div>

            <button type="button" className="big" disabled={loading} onClick={handleSegment}>
              {loading ? 'Working…' : 'Create customer groups'}
            </button>

            {error && currentStep >= 2 && !segments && (
              <div className="tip-box error" style={{ marginTop: '0.75rem' }}>
                {error}
              </div>
            )}

            {segments && (
              <div className="tip-box success" style={{ marginTop: '0.75rem' }}>
                <strong>Step 2 complete!</strong> Customers are sorted into {k} groups. Quality
                score: {segments.metrics.silhouette_score.toFixed(2)} (closer to 1.0 is better).
              </div>
            )}
          </>
        )}
      </StepCard>

      {segments && (
        <>
          <StepCard
            n={3}
            title="See your results"
            subtitle="Each color is a customer group. Dots that cluster together behave alike."
            done={step2Done}
            active={currentStep === 3}
          >
            <p className="chart-caption">
              Horizontal = monthly spending · Vertical = average balance · Each dot = one customer
            </p>
            <div className="chart-card">
              <ResponsiveContainer width="100%" height={340}>
                <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#c8d4e6" />
                  <XAxis
                    type="number"
                    dataKey="monthly_spend"
                    name="Monthly spend"
                    stroke="#5a6b7d"
                    tick={{ fill: '#5a6b7d', fontSize: 12 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="avg_balance"
                    name="Balance"
                    stroke="#5a6b7d"
                    tick={{ fill: '#5a6b7d', fontSize: 12 }}
                  />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    contentStyle={{ background: '#fff', border: '1px solid #c8d4e6', borderRadius: 8 }}
                  />
                  <Legend />
                  {scatterGroups.map((g) => (
                    <Scatter
                      key={g.segmentId}
                      name={g.name}
                      data={g.customers}
                      fill={COLORS[g.segmentId % COLORS.length]}
                    />
                  ))}
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </StepCard>

          <section className="card">
            <h2 className="step-title" style={{ marginTop: 0 }}>
              Top spenders in each group
            </h2>
            <p className="step-subtitle">
              Useful for marketing: who are the highest-spending customers in each segment?
            </p>
            {topPerSegment.map((group) => (
              <div key={group.segment_id} className="segment-block">
                <h3>{group.segment_name}</h3>
                <table>
                  <thead>
                    <tr>
                      <th>Customer</th>
                      <th>Transactions</th>
                      <th>Balance</th>
                      <th>Monthly spend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.top.map((c) => (
                      <tr key={c.customer_id}>
                        <td>{c.customer_id}</td>
                        <td>{c.txn_count}</td>
                        <td>${c.avg_balance.toLocaleString()}</td>
                        <td>${c.monthly_spend.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </section>

          <StepCard
            n={4}
            title="Generate stakeholder summary (lab)"
            subtitle="Real inference step — Hugging Face summarization when configured, smart fallback otherwise."
            done={step4Done}
            active={currentStep === 4}
          >
            <div className="tip-box">
              <strong>Lab deliverable:</strong> Turn your segments into a short summary a marketing lead
              could read. This calls the portfolio inference API (same pattern as production ML apps).
            </div>

            <button
              type="button"
              className="big"
              disabled={summarizeLoading}
              onClick={handleSummarize}
            >
              {summarizeLoading ? 'Generating summary…' : 'Summarize my segments'}
            </button>

            {summarizeError && (
              <div className="tip-box error" style={{ marginTop: '0.75rem' }}>
                {summarizeError}
              </div>
            )}

            {stakeholderSummary && (
              <div className="summary-panel">
                <div className="summary-meta">
                  <span className="summary-badge">
                    {stakeholderSummary.source === 'huggingface'
                      ? `HF · ${stakeholderSummary.model}`
                      : 'Local lab coach (add HF_TOKEN for live inference)'}
                  </span>
                  <button type="button" className="ghost copy-btn" onClick={() => void copySummary()}>
                    Copy lab report
                  </button>
                </div>
                <p className="summary-text">{stakeholderSummary.summary}</p>
                <ul className="summary-bullets">
                  {stakeholderSummary.bullets.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
                <div className="proof-actions">
                  <button
                    type="button"
                    className="big"
                    disabled={proofLoading}
                    onClick={handleSaveProof}
                  >
                    {proofLoading ? 'Saving proof…' : 'Save & get shareable proof link'}
                  </button>
                </div>
                {proofError && (
                  <div className="tip-box error" style={{ marginTop: '0.75rem' }}>
                    {proofError}
                  </div>
                )}
                {proofUrl && (
                  <div className="tip-box success" style={{ marginTop: '0.75rem' }}>
                    <strong>Proof link ready</strong> — add to resume or LinkedIn:{' '}
                    <a href={proofUrl} target="_blank" rel="noopener noreferrer">
                      {proofUrl}
                    </a>
                  </div>
                )}
              </div>
            )}
          </StepCard>

          <div className="tip-box success">
            <strong>You did it!</strong> You loaded data, ran customer grouping, explored segments
            {stakeholderSummary ? ', and generated a stakeholder summary' : ''}.{' '}
            <a href="http://localhost:3200/build/projects/customer-segmentation-lab#step-guide">
              Open Build Lab to mark your steps complete
            </a>
            .
          </div>
        </>
      )}

      <details className="glossary card">
        <summary>What do these words mean?</summary>
        <ul>
          {GLOSSARY.map((g) => (
            <li key={g.term}>
              <strong>{g.term}:</strong> {g.plain}
            </li>
          ))}
        </ul>
      </details>

      <p className="footer-note">
        Learning project · Columbia / Willamette Valley Bank style analytics · Portfolio Build Lab
      </p>
    </div>
  );
}
