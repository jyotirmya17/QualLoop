import React from 'react';
import {
  Activity,
  Layers,
  BarChart3,
  ShieldCheck,
  Play,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { SimulationRun } from '../types/api';

interface HeaderProps {
  activeTab: 'portfolio' | 'benchmark' | 'audit' | 'health';
  setActiveTab: (tab: 'portfolio' | 'benchmark' | 'audit' | 'health') => void;
  runs: SimulationRun[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  onOpenRunner: () => void;
  isBackendHealthy: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  runs,
  selectedRunId,
  onSelectRun,
  onOpenRunner,
  isBackendHealthy,
  isRefreshing,
  onRefresh,
}) => {
  return (
    <div>
      {/* Mandatory Simulated Data Banner */}
      <div className="simulation-banner" role="alert">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertTriangle size={18} color="#f59e0b" />
          <span>⚠ SIMULATED DATA — NOT CONNECTED TO A LIVE AD ACCOUNT</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="badge">ISOLATED SYNTHETIC ENGINE</span>
          <span style={{ fontSize: '0.78rem', color: '#fde68a', opacity: 0.85 }}>
            Empirical Bayesian Evaluation Active
          </span>
        </div>
      </div>

      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">
            <Activity size={24} color="#ffffff" />
          </div>
          <div>
            <h1 className="brand-title">QualLoop</h1>
            <p className="brand-subtitle">
              Uncertainty-Aware Lead Qualification & Advertising Feedback Loop
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="nav-tabs">
          <button
            className={`nav-tab-btn ${activeTab === 'portfolio' ? 'active' : ''}`}
            onClick={() => setActiveTab('portfolio')}
          >
            <Layers size={16} />
            <span>Portfolio & Ads</span>
          </button>
          <button
            className={`nav-tab-btn ${activeTab === 'benchmark' ? 'active' : ''}`}
            onClick={() => setActiveTab('benchmark')}
          >
            <BarChart3 size={16} />
            <span>Benchmark Lab</span>
          </button>
          <button
            className={`nav-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            <ShieldCheck size={16} />
            <span>Decision Audit</span>
          </button>
          <button
            className={`nav-tab-btn ${activeTab === 'health' ? 'active' : ''}`}
            onClick={() => setActiveTab('health')}
          >
            <Activity size={16} />
            <span>System Health</span>
          </button>
        </nav>

        {/* Actions & Simulation selector */}
        <div className="header-actions">
          {runs.length > 0 && activeTab === 'portfolio' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontWeight: 600 }}>
                RUN:
              </span>
              <select
                className="form-select"
                style={{ padding: '6px 12px', fontSize: '0.8rem', minWidth: '190px' }}
                value={selectedRunId || ''}
                onChange={(e) => onSelectRun(e.target.value)}
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.scenario_name} (seed {r.seed})
                  </option>
                ))}
              </select>
            </div>
          )}

          <button
            className="btn btn-secondary"
            onClick={onRefresh}
            title="Refresh active view"
            disabled={isRefreshing}
          >
            <RefreshCw size={15} className={isRefreshing ? 'animate-spin' : ''} />
          </button>

          <button className="btn btn-primary" onClick={onOpenRunner}>
            <Play size={16} fill="white" />
            <span>Run Scenario</span>
          </button>

          {/* Connection Pill */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 10px',
              borderRadius: '999px',
              background: isBackendHealthy ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
              border: `1px solid ${isBackendHealthy ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
              fontSize: '0.72rem',
              fontWeight: 600,
              color: isBackendHealthy ? '#34d399' : '#fb7185',
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: isBackendHealthy ? '#10b981' : '#f43f5e',
                boxShadow: isBackendHealthy ? '0 0 8px #10b981' : '0 0 8px #f43f5e',
              }}
            />
            <span>{isBackendHealthy ? 'API ONLINE' : 'API OFFLINE'}</span>
          </div>
        </div>
      </header>
    </div>
  );
};
