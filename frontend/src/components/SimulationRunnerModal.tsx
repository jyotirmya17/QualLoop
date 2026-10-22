import React, { useState } from 'react';
import { X, Play, Sparkles, Info } from 'lucide-react';

interface SimulationRunnerModalProps {
  scenarios: string[];
  isOpen: boolean;
  onClose: () => void;
  onRunSimulation: (scenario: string, seed: number) => Promise<void>;
  isLoading: boolean;
}

const SCENARIO_DESCRIPTIONS: Record<string, string> = {
  healthy_campaign: 'Balanced performance across ads with standard lead volume and healthy qualification rates.',
  good_ad_low_reachability: 'High customer buying intent but low phone contactability. Prevents falsely pausing reach-limited winners.',
  bad_ad_high_engagement: 'High CTR and cheap leads, but very poor qualification. Tests detection of misleading engagement vanity metrics.',
  small_sample_trap: 'Few leads with misleadingly high or low early rates. Demonstrates wide credible intervals avoiding premature decisions.',
  delayed_conversion_trap: 'Leads take up to 14 days to resolve qualification. Demonstrates outcome maturity window gating.',
  creative_fatigue: 'Performance starts strong then decays over time due to ad audience burnout.',
  mixed_portfolio: 'Heterogeneous mix of good, bad, reachability-limited, and fatigue-prone creatives.',
  high_cpql: 'High quality leads with elevated customer acquisition costs, testing CPQL threshold reallocation.',
  sudden_deterioration: 'Creative performs well for initial period, then drops abruptly, triggering abnormal change detection.',
};

export const SimulationRunnerModal: React.FC<SimulationRunnerModalProps> = ({
  scenarios,
  isOpen,
  onClose,
  onRunSimulation,
  isLoading,
}) => {
  const [selectedScenario, setSelectedScenario] = useState<string>('mixed_portfolio');
  const [seed, setSeed] = useState<number>(42);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onRunSimulation(selectedScenario, seed);
    onClose();
  };

  const handleRandomizeSeed = () => {
    setSeed(Math.floor(Math.random() * 90000) + 1000);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: '8px',
                background: 'rgba(99, 102, 241, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid rgba(99, 102, 241, 0.3)',
              }}
            >
              <Sparkles size={18} color="#818cf8" />
            </div>
            <div>
              <h2 style={{ fontSize: '1.25rem' }}>Run Synthetic Simulation</h2>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Generate reproducible advertising and lead cohorts
              </p>
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Scenario Preset</label>
            <select
              className="form-select"
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
            >
              {scenarios.map((sc) => (
                <option key={sc} value={sc}>
                  {sc.replace(/_/g, ' ').toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          {/* Scenario description callout */}
          <div
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              background: 'rgba(99, 102, 241, 0.08)',
              border: '1px solid rgba(99, 102, 241, 0.2)',
              marginBottom: '18px',
              display: 'flex',
              gap: '10px',
              alignItems: 'flex-start',
            }}
          >
            <Info size={16} color="#818cf8" style={{ marginTop: '2px', flexShrink: 0 }} />
            <p style={{ fontSize: '0.82rem', color: '#c7d2fe', lineHeight: 1.4 }}>
              {SCENARIO_DESCRIPTIONS[selectedScenario] || 'Synthetic advertising experiment preset.'}
            </p>
          </div>

          <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="form-label">Random Seed (Deterministic)</label>
              <button
                type="button"
                onClick={handleRandomizeSeed}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#818cf8',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Randomize Seed
              </button>
            </div>
            <input
              type="number"
              className="form-input mono"
              value={seed}
              onChange={(e) => setSeed(parseInt(e.target.value) || 0)}
              required
            />
          </div>

          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '12px',
              marginTop: '28px',
            }}
          >
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={isLoading}>
              <Play size={16} fill="white" />
              <span>{isLoading ? 'Running Engine...' : 'Run Simulation'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
