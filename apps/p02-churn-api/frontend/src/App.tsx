import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchHistory,
  getHealth,
  predictBatch,
  predictOne,
  type CustomerInput,
  type Health,
  type LogItem,
  type Prediction,
} from './api';

const defaultCustomer: CustomerInput = {
  customer_id: 'CUST-9001',
  tenure_months: 8,
  monthly_charges: 85.5,
  total_charges: 620.0,
  contract_type: 'month',
  support_calls: 4,
};

function RiskBadge({ band }: { band: string }) {
  const cls = band === 'low' || band === 'medium' || band === 'high' ? band : 'medium';
  return <span className={`badge ${cls}`}>{band}</span>;
}

function buildBatchDemo(n: number): CustomerInput[] {
  return Array.from({ length: n }, (_, i) => ({
    customer_id: `BATCH-${String(i + 1).padStart(4, '0')}`,
    tenure_months: 3 + (i % 48),
    monthly_charges: 35 + (i % 70),
    total_charges: 200 + i * 15,
    contract_type: (['month', 'year', 'two_year'] as const)[i % 3],
    support_calls: i % 6,
  }));
}

function exportCsv(rows: LogItem[]) {
  const header = 'id,created_at,customer_id,churn_probability,risk_band,model_version';
  const lines = rows.map(
    (r) =>
      `${r.id},${r.created_at},${r.customer_id},${r.churn_probability},${r.risk_band},${r.model_version}`,
  );
  const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'churn_predictions.csv';
  a.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [form, setForm] = useState<CustomerInput>(defaultCustomer);
  const [latest, setLatest] = useState<Prediction | null>(null);
  const [history, setHistory] = useState<LogItem[]>([]);
  const [riskFilter, setRiskFilter] = useState<'all' | 'low' | 'medium' | 'high'>('all');
  const [sortDesc, setSortDesc] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refreshHistory = useCallback(async () => {
    const items = await fetchHistory(1, 100);
    setHistory(items);
  }, []);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
    refreshHistory().catch(() => setHistory([]));
  }, [refreshHistory]);

  async function handlePredict() {
    setError('');
    setLoading(true);
    try {
      const result = await predictOne(form);
      setLatest(result);
      await refreshHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Prediction failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleBatch100() {
    setError('');
    setLoading(true);
    try {
      await predictBatch(buildBatchDemo(100));
      setLatest(null);
      await refreshHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Batch prediction failed');
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    let rows = [...history];
    if (riskFilter !== 'all') {
      rows = rows.filter((r) => r.risk_band === riskFilter);
    }
    rows.sort((a, b) =>
      sortDesc
        ? b.churn_probability - a.churn_probability
        : a.churn_probability - b.churn_probability,
    );
    return rows;
  }, [history, riskFilter, sortDesc]);

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '1.5rem 1rem' }}>
      <header style={{ marginBottom: '1.25rem' }}>
        <p className="muted">Willamette Valley Bank · Portfolio Project 02</p>
        <h1 style={{ margin: '0.2rem 0' }}>Churn Prediction API</h1>
        <p className="muted">Banker dashboard for churn scores, audit history, and batch scoring.</p>
        <p style={{ marginTop: '0.5rem' }}>
          API:{' '}
          {!health ? (
            <span className="error">offline — train model & start backend on :8001</span>
          ) : (
            <span style={{ color: 'var(--low)' }}>
              ok · db {health.db_ok ? 'connected' : 'down'} · model{' '}
              {health.model_loaded ? health.model_version : 'missing'}
            </span>
          )}
        </p>
      </header>

      <section className="card" style={{ marginBottom: '1rem' }}>
        <h2 style={{ marginTop: 0 }}>Score a customer</h2>
        <div className="grid-form">
          <div>
            <label>Customer ID</label>
            <input
              value={form.customer_id}
              onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
            />
          </div>
          <div>
            <label>Tenure (months)</label>
            <input
              type="number"
              value={form.tenure_months}
              onChange={(e) => setForm({ ...form, tenure_months: Number(e.target.value) })}
            />
          </div>
          <div>
            <label>Monthly charges</label>
            <input
              type="number"
              step="0.01"
              value={form.monthly_charges}
              onChange={(e) => setForm({ ...form, monthly_charges: Number(e.target.value) })}
            />
          </div>
          <div>
            <label>Total charges</label>
            <input
              type="number"
              step="0.01"
              value={form.total_charges}
              onChange={(e) => setForm({ ...form, total_charges: Number(e.target.value) })}
            />
          </div>
          <div>
            <label>Contract</label>
            <select
              value={form.contract_type}
              onChange={(e) =>
                setForm({
                  ...form,
                  contract_type: e.target.value as CustomerInput['contract_type'],
                })
              }
            >
              <option value="month">Month-to-month</option>
              <option value="year">One year</option>
              <option value="two_year">Two year</option>
            </select>
          </div>
          <div>
            <label>Support calls</label>
            <input
              type="number"
              value={form.support_calls}
              onChange={(e) => setForm({ ...form, support_calls: Number(e.target.value) })}
            />
          </div>
        </div>
        <div className="toolbar" style={{ marginTop: '1rem' }}>
          <button type="button" disabled={loading} onClick={handlePredict}>
            {loading ? 'Scoring…' : 'Predict churn'}
          </button>
          <button type="button" className="ghost" disabled={loading} onClick={handleBatch100}>
            Run batch (100)
          </button>
        </div>
        {error && <p className="error" style={{ marginTop: '0.75rem' }}>{error}</p>}
        {latest && (
          <div style={{ marginTop: '1rem' }}>
            <p>
              <strong>{latest.customer_id}</strong> — {(latest.churn_probability * 100).toFixed(1)}%{' '}
              <RiskBadge band={latest.risk_band} />
            </p>
            <ul className="muted">
              {latest.top_drivers.map((d) => (
                <li key={d.feature}>
                  {d.feature}: {d.impact} ({d.direction})
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Prediction audit log</h2>
        <div className="toolbar">
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value as typeof riskFilter)}
            style={{ width: 'auto', minWidth: 140 }}
          >
            <option value="all">All risk bands</option>
            <option value="high">High only</option>
            <option value="medium">Medium only</option>
            <option value="low">Low only</option>
          </select>
          <button type="button" className="ghost" onClick={() => setSortDesc((v) => !v)}>
            Sort: {sortDesc ? 'highest risk first' : 'lowest risk first'}
          </button>
          <button
            type="button"
            className="ghost"
            disabled={filtered.length === 0}
            onClick={() => exportCsv(filtered)}
          >
            Export CSV
          </button>
          <button type="button" className="ghost" onClick={() => refreshHistory()}>
            Refresh
          </button>
        </div>

        {loading && history.length === 0 ? (
          <p className="muted">Loading history…</p>
        ) : filtered.length === 0 ? (
          <p className="muted">No predictions yet. Score a customer or run the batch demo.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time (UTC)</th>
                  <th>Customer</th>
                  <th>Probability</th>
                  <th>Risk</th>
                  <th className="hide-mobile">Model</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.id}>
                    <td>{row.created_at.slice(0, 19)}</td>
                    <td>{row.customer_id}</td>
                    <td>{(row.churn_probability * 100).toFixed(1)}%</td>
                    <td>
                      <RiskBadge band={row.risk_band} />
                    </td>
                    <td className="hide-mobile muted">{row.model_version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
