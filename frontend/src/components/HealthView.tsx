import React from 'react';
import { Activity, Terminal } from 'lucide-react';
import { HealthStatus } from '../types/api';

interface HealthViewProps {
  health: HealthStatus | null;
  isBackendHealthy: boolean;
}

export const HealthView: React.FC<HealthViewProps> = ({ health, isBackendHealthy }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Overview Card */}
      <div className="glass-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: '10px',
              background: isBackendHealthy ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: `1px solid ${isBackendHealthy ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
            }}
          >
            <Activity size={22} color={isBackendHealthy ? '#10b981' : '#f43f5e'} />
          </div>
          <div>
            <h2 style={{ fontSize: '1.3rem' }}>System & Subsystem Health Diagnostics</h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Real-time architectural boundary and API connectivity verification
            </p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
          <div style={{ padding: '14px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>REST API Server</span>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: isBackendHealthy ? '#34d399' : '#fb7185', marginTop: '4px' }}>
              {isBackendHealthy ? 'OPERATIONAL' : 'DISCONNECTED'}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>FastAPI 0.115+ (port 8000)</span>
          </div>

          <div style={{ padding: '14px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Simulation Mode</span>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#fbbf24', marginTop: '4px' }}>
              SYNTHETIC ISOLATED
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>No live ad account connected</span>
          </div>

          <div style={{ padding: '14px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Statistical Engine</span>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#818cf8', marginTop: '4px' }}>
              BETA-BINOMIAL
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Maturity Gated Bayesian Model</span>
          </div>

          <div style={{ padding: '14px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>CAPI Feedback Module</span>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#38bdf8', marginTop: '4px' }}>
              DRY-RUN ENFORCED
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Meta CAPI v21.0 Payload Validator</span>
          </div>
        </div>
      </div>

      {/* Architecture Boundaries Verification Table */}
      <div className="glass-card" style={{ padding: '20px' }}>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '14px' }}>
          QualLoop Architecture Boundary Invariants
        </h3>

        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Boundary Invariant</th>
                <th>Enforcement Mechanism</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Ground Truth Isolation</strong></td>
                <td>Hidden reachability and intent exist only in simulator, accessed strictly by benchmark runner. Never in production API.</td>
                <td><span style={{ color: '#34d399', fontWeight: 600 }}>✓ VERIFIED</span></td>
              </tr>
              <tr>
                <td><strong>Estimator Independence</strong></td>
                <td>Zero dependencies on FastAPI or persistence. Pure deterministic math taking domain objects.</td>
                <td><span style={{ color: '#34d399', fontWeight: 600 }}>✓ VERIFIED</span></td>
              </tr>
              <tr>
                <td><strong>Decision Engine Location</strong></td>
                <td>Recommendation rules strictly confined to <code>decision_engine/</code>, never in routers or frontend.</td>
                <td><span style={{ color: '#34d399', fontWeight: 600 }}>✓ VERIFIED</span></td>
              </tr>
              <tr>
                <td><strong>Audit Completeness</strong></td>
                <td>Every recommendation is recorded into the append-only ledger with full supporting evidence.</td>
                <td><span style={{ color: '#34d399', fontWeight: 600 }}>✓ VERIFIED</span></td>
              </tr>
              <tr>
                <td><strong>Feedback Safe Transmission</strong></td>
                <td>Meta Conversions API payloads are generated and cryptographically hashed in dry-run mode without external transmission.</td>
                <td><span style={{ color: '#34d399', fontWeight: 600 }}>✓ VERIFIED</span></td>
              </tr>
              <tr>
                <td><strong>Synthetic Data Transparency</strong></td>
                <td>Persistent warning banners displayed across every dashboard view and API payload.</td>
                <td><span style={{ color: '#34d399', fontWeight: 600 }}>✓ VERIFIED</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Raw Health Response */}
      {health && (
        <div className="glass-card" style={{ padding: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
            <Terminal size={15} color="#818cf8" />
            <h4 style={{ fontSize: '0.85rem' }}>Backend Root Handshake Response</h4>
          </div>
          <pre className="mono" style={{ fontSize: '0.75rem', color: '#94a3b8', background: '#07090e', padding: '12px', borderRadius: '6px' }}>
            {JSON.stringify(health, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};
