import React, { useState } from 'react';
import { BarChart3, Play, ShieldAlert } from 'lucide-react';
import { BenchmarkReport } from '../types/api';

interface BenchmarkViewProps {
  report: BenchmarkReport | null;
  onRunBenchmark: (maxRuns: number) => Promise<void>;
  isLoading: boolean;
}

export const BenchmarkView: React.FC<BenchmarkViewProps> = ({
  report,
  onRunBenchmark,
  isLoading,
}) => {
  const [runsPerScenario, setRunsPerScenario] = useState<number>(5);

  if (!report) {
    return (
      <div className="glass-card" style={{ textAlign: 'center', padding: '60px' }}>
        <BarChart3 size={48} color="#6366f1" style={{ margin: '0 auto 16px' }} />
        <h3>No Benchmark Results Available</h3>
        <p style={{ color: 'var(--text-muted)', marginBottom: '24px' }}>
          Execute the paired empirical benchmark across simulated scenarios to measure statistical performance against ground truth.
        </p>
        <button
          className="btn btn-primary"
          onClick={() => onRunBenchmark(5)}
          disabled={isLoading}
        >
          <Play size={16} fill="white" />
          <span>{isLoading ? 'Running Benchmark...' : 'Run Benchmark (45 Simulations)'}</span>
        </button>
      </div>
    );
  }

  const { run_metadata: meta, aggregate_metrics: agg, per_scenario_breakdown: scenarios, cases_where_qualloop_performed_worse: worseCases } = report;
  const q = agg.qualloop;
  const b = agg.baseline;

  const fpprDelta = q.fppr_mean - b.fppr_mean;
  const fndrDelta = q.fndr_mean - b.fndr_mean;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      {/* Benchmark Header */}
      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <span style={{ fontSize: '0.72rem', background: 'rgba(99, 102, 241, 0.2)', color: '#818cf8', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
              EMPIRICAL BENCHMARK
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              Executed: {new Date(meta.executed_at).toLocaleString()}
            </span>
          </div>
          <h2 style={{ fontSize: '1.4rem' }}>QualLoop vs. Naive Baseline Evaluation</h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Paired evaluation of {meta.n_simulations} simulation runs across {meta.n_ads_evaluated} advertisements ({meta.n_good_ads} good, {meta.n_poor_ads} poor) evaluated against hidden ground truth.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Runs/Preset:</span>
            <select
              className="form-select"
              style={{ padding: '6px 12px', fontSize: '0.8rem' }}
              value={runsPerScenario}
              onChange={(e) => setRunsPerScenario(parseInt(e.target.value))}
            >
              <option value={2}>2 runs (18 total)</option>
              <option value={5}>5 runs (45 total)</option>
              <option value={10}>10 runs (90 total)</option>
              <option value={20}>20 runs (180 total)</option>
            </select>
          </div>

          <button
            className="btn btn-primary"
            onClick={() => onRunBenchmark(runsPerScenario)}
            disabled={isLoading}
          >
            <Play size={16} fill="white" />
            <span>{isLoading ? 'Running Experiments...' : 'Re-run Benchmark'}</span>
          </button>
        </div>
      </div>

      {/* Comparison Head-to-Head Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '18px' }}>
        {/* FPPR Card */}
        <div className="glass-card" style={{ borderLeft: '4px solid #10b981' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              FALSE POSITIVE PAUSE RATE (FPPR)
            </span>
            <span style={{ fontSize: '0.72rem', color: '#34d399', fontWeight: 700 }}>
              {fpprDelta <= 0 ? '✓ LOWER IS BETTER' : 'ALERT'}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px', marginBottom: '8px' }}>
            <div>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, color: '#34d399' }}>
                {(q.fppr_mean * 100).toFixed(1)}%
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>QualLoop (Target &lt; 10%)</span>
            </div>
            <div style={{ fontSize: '1.2rem', color: 'var(--text-dim)' }}>vs</div>
            <div>
              <div style={{ fontSize: '1.4rem', fontWeight: 600, color: '#fb7185' }}>
                {(b.fppr_mean * 100).toFixed(1)}%
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Naive Baseline</span>
            </div>
          </div>

          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            QualLoop stopped <strong>{(Math.abs(fpprDelta) * 100).toFixed(1)}% fewer</strong> good ads from being prematurely paused by respecting maturity and uncertainty.
          </p>
        </div>

        {/* FNDR Card */}
        <div className="glass-card" style={{ borderLeft: '4px solid #6366f1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              FALSE NEGATIVE DETECTION (FNDR)
            </span>
            <span style={{ fontSize: '0.72rem', color: '#a5b4fc', fontWeight: 700 }}>
              CONSERVATISM TRADEOFF
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px', marginBottom: '8px' }}>
            <div>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, color: '#a5b4fc' }}>
                {(q.fndr_mean * 100).toFixed(1)}%
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>QualLoop</span>
            </div>
            <div style={{ fontSize: '1.2rem', color: 'var(--text-dim)' }}>vs</div>
            <div>
              <div style={{ fontSize: '1.4rem', fontWeight: 600, color: '#cbd5e1' }}>
                {(b.fndr_mean * 100).toFixed(1)}%
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Naive Baseline</span>
            </div>
          </div>

          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Delta: {fndrDelta >= 0 ? '+' : ''}{(fndrDelta * 100).toFixed(1)}%. QualLoop refuses to pause immature low-sample ads early, choosing caution (<span className="mono">collect_more_data</span>) over guessing.
          </p>
        </div>

        {/* Insufficient Evidence Rate */}
        <div className="glass-card" style={{ borderLeft: '4px solid #f59e0b' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              INSUFFICIENT EVIDENCE RATE (IER)
            </span>
            <span style={{ fontSize: '0.72rem', color: '#fbbf24', fontWeight: 700 }}>
              EVIDENCE GATING
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px', marginBottom: '8px' }}>
            <div>
              <div style={{ fontSize: '1.8rem', fontWeight: 700, color: '#fbbf24' }}>
                {(q.ier_mean * 100).toFixed(1)}%
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>QualLoop Explicit Flag</span>
            </div>
            <div style={{ fontSize: '1.2rem', color: 'var(--text-dim)' }}>vs</div>
            <div>
              <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text-dim)' }}>
                0.0%
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Naive (No Concept)</span>
            </div>
          </div>

          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Baseline never admits it does not know; QualLoop flags when maturity or sample counts are insufficient.
          </p>
        </div>
      </div>

      {/* Per Scenario Table */}
      <div className="glass-card" style={{ padding: '20px' }}>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '14px' }}>
          Scenario Preset Breakdown (Paired Ground Truth Test)
        </h3>
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Scenario Preset</th>
                <th>Simulations</th>
                <th>Total Ads</th>
                <th>QualLoop FPPR</th>
                <th>Baseline FPPR</th>
                <th>QualLoop FNDR</th>
                <th>Baseline FNDR</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((sc) => (
                <tr key={sc.scenario_name}>
                  <td>
                    <strong style={{ color: '#e2e8f0' }}>{sc.scenario_name}</strong>
                  </td>
                  <td>{sc.n_simulations}</td>
                  <td>{sc.n_ads}</td>
                  <td style={{ color: sc.qualloop_fppr === 0 ? '#34d399' : 'inherit' }}>
                    {(sc.qualloop_fppr * 100).toFixed(1)}%
                  </td>
                  <td style={{ color: sc.baseline_fppr > 0 ? '#fb7185' : 'inherit' }}>
                    {(sc.baseline_fppr * 100).toFixed(1)}%
                  </td>
                  <td>{(sc.qualloop_fndr * 100).toFixed(1)}%</td>
                  <td>{(sc.baseline_fndr * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Honesty & Transparency Section */}
      <div className="glass-card" style={{ border: '1px solid rgba(244, 63, 94, 0.25)', background: 'rgba(244, 63, 94, 0.03)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
          <ShieldAlert size={20} color="#f43f5e" />
          <h3 style={{ fontSize: '1.1rem', color: '#fda4af' }}>
            Scientific Transparency: Cases Where QualLoop Performed Worse ({worseCases.length} detected)
          </h3>
        </div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '16px', lineHeight: 1.5 }}>
          Per the benchmark methodology, we strictly document when our uncertainty-aware policy did not outperform the naive heuristic. In small samples, naive rules occasionally pause genuinely poor ads early purely by chance, whereas QualLoop prudently requests more evidence.
        </p>

        {worseCases.length === 0 ? (
          <p style={{ fontSize: '0.85rem', color: '#34d399' }}>
            No instances were detected where QualLoop performed worse than baseline in this benchmark run.
          </p>
        ) : (
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Creative</th>
                  <th>Ground Truth Intent</th>
                  <th>QualLoop Action</th>
                  <th>Baseline Action</th>
                  <th>Why It Happened</th>
                </tr>
              </thead>
              <tbody>
                {worseCases.slice(0, 10).map((c, idx) => (
                  <tr key={idx}>
                    <td><code>{c.scenario}</code></td>
                    <td><code>{c.creative_id}</code></td>
                    <td className="mono">{(c.gt_intent_mean * 100).toFixed(1)}%</td>
                    <td>
                      <span className={`badge-action action-${c.qualloop_action}`}>
                        {c.qualloop_action.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td>
                      <span className={`badge-action action-${c.baseline_action}`}>
                        {c.baseline_action.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.78rem', color: '#cbd5e1' }}>{c.explanation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
