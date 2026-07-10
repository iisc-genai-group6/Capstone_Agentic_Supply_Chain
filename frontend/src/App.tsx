import { useEffect, useState } from 'react';
import { getHealth, runPipeline, getRuns, getSignals } from './api';
import type { HealthResponse, RunResponse, SignalResponse, RunListResponse } from './types';
import './App.css';

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<RunResponse | null>(null);
  const [runs, setRuns] = useState<RunListResponse | null>(null);
  const [signals, setSignals] = useState<SignalResponse | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  async function refreshDashboard() {
    try {
      const [healthData, runsData, signalsData] = await Promise.all([getHealth(), getRuns(), getSignals()]);
      setHealth(healthData);
      setRuns(runsData);
      setSignals(signalsData);
      setError(null);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      setError('A dashboard refresh failed.');
    }
  }

  useEffect(() => {
    void refreshDashboard();
    const intervalId = window.setInterval(() => {
      void refreshDashboard();
    }, 15000);

    return () => window.clearInterval(intervalId);
  }, []);

  async function handleRun() {
    setError(null);
    setLoading(true);
    try {
      const data = await runPipeline({ scenario_name: null, use_pending_signals: true });
      setRunResult(data);
      await refreshDashboard();
    } catch (err) {
      setError('Pipeline run failed.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>Agentic SCD Dashboard</h1>
          <p>Live operational view for signals, runs, and system health.</p>
        </div>
        <div className="topbar-actions">
          <span className="status-pill">Auto-refresh • every 15s</span>
          <button onClick={() => void refreshDashboard()}>
            Refresh
          </button>
          <button onClick={handleRun} disabled={loading}>
            {loading ? 'Running...' : 'Run pipeline'}
          </button>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}
      <div className="meta-row">
        <span className="meta-chip">Live data</span>
        {lastUpdated ? <span className="meta-chip muted">Last updated {lastUpdated}</span> : null}
      </div>

      <section className="section-grid">
        <article className="card">
          <h2>System health</h2>
          {health ? (
            <div className="health-grid">
              <div>
                <strong>Status</strong>
                <p>{health.status}</p>
              </div>
              <div>
                <strong>Database</strong>
                <p>{health.database}</p>
              </div>
              <div>
                <strong>LLM mode</strong>
                <p>{health.llm_mode}</p>
              </div>
              <div>
                <strong>Data home</strong>
                <p>{health.data_dir}</p>
              </div>
            </div>
          ) : (
            <p>Loading health...</p>
          )}
        </article>

        <article className="card large-card">
          <h2>Latest run</h2>
          {runResult ? (
            <pre className="json-box">{JSON.stringify(runResult, null, 2)}</pre>
          ) : (
            <p>Run the pipeline to see results here.</p>
          )}
        </article>
      </section>

      <section className="section-grid">
        <article className="card">
          <h2>Recent runs</h2>
          {runs?.runs?.length ? (
            <table>
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Scenario</th>
                  <th>Route</th>
                  <th>Max severity</th>
                </tr>
              </thead>
              <tbody>
                {runs.runs.map((run) => (
                  <tr key={run.run_id}>
                    <td>{run.run_id}</td>
                    <td>{run.scenario_name ?? 'N/A'}</td>
                    <td>{run.route ?? 'N/A'}</td>
                    <td>{run.max_severity ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No runs available yet.</p>
          )}
        </article>

        <article className="card">
          <h2>Recent signals</h2>
          {signals?.signals?.length ? (
            <ul className="signal-list">
              {signals.signals.slice(0, 8).map((signal) => (
                <li key={signal.signal_id}>
                  <strong>{signal.title}</strong>
                  <div>{signal.source}</div>
                  <div className="signal-meta">
                    <span>{signal.region}</span>
                    <span>{signal.severity_hint ?? 'unknown'}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p>No signals available yet.</p>
          )}
        </article>
      </section>
    </div>
  );
}

export default App;
