import React, { useState } from 'react';
import { Search, Filter, Calendar, Code, ChevronDown, ChevronRight } from 'lucide-react';
import { Decision } from '../types/api';

interface AuditTrailViewProps {
  decisions: Decision[];
  auditEvents: any[];
  isLoading: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export const AuditTrailView: React.FC<AuditTrailViewProps> = ({
  decisions,
  auditEvents,
  isLoading,
  error,
  onRetry,
}) => {
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [actionFilter, setActionFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filteredDecisions = decisions.filter((d) => {
    if (actionFilter !== 'all' && d.action !== actionFilter) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      return (
        d.advertisement_id.toLowerCase().includes(term) ||
        d.reason.toLowerCase().includes(term) ||
        d.id.toLowerCase().includes(term)
      );
    }
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <span style={{ fontSize: '0.72rem', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
              APPEND-ONLY AUDIT LEDGER
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              {decisions.length} Decisions Logged &bull; {auditEvents.length} Raw Events
            </span>
          </div>
          <h2 style={{ fontSize: '1.4rem' }}>Decision Audit Trail & Evidence Log</h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Every recommendation produced by the decision engine is immutably logged with its supporting statistical snapshot, policy version, and rationale.
          </p>
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Filter size={14} color="var(--text-dim)" />
            <select
              className="form-select"
              style={{ padding: '6px 12px', fontSize: '0.8rem' }}
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
            >
              <option value="all">All Actions</option>
              <option value="continue_monitoring">Continue Monitoring</option>
              <option value="collect_more_data">Collect More Data</option>
              <option value="investigate_low_reachability">Investigate Low Reachability</option>
              <option value="refresh_creative">Refresh Creative</option>
              <option value="consider_pause">Consider Pause</option>
              <option value="consider_reallocate">Consider Reallocate</option>
              <option value="flag_insufficient_evidence">Insufficient Evidence</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', position: 'relative' }}>
            <input
              type="text"
              className="form-input"
              style={{ padding: '6px 12px 6px 30px', fontSize: '0.8rem', width: '220px' }}
              placeholder="Search Ad ID or reason..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            <Search size={14} color="var(--text-dim)" style={{ position: 'absolute', left: 10 }} />
          </div>
        </div>
      </div>

      {/* Decisions List */}
      <div className="glass-card" style={{ padding: '20px' }}>
        <h3 style={{ fontSize: '1.1rem', marginBottom: '16px' }}>
          Audited Decisions ({filteredDecisions.length})
        </h3>

        {error && (
          <div
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#f87171',
              marginBottom: '16px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span style={{ fontSize: '0.85rem' }}>Failed to retrieve audit records: {error}</span>
            {onRetry && (
              <button
                className="btn btn-secondary"
                style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                onClick={onRetry}
              >
                Retry
              </button>
            )}
          </div>
        )}

        {filteredDecisions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-dim)' }}>
            {isLoading ? 'Loading audit records...' : error ? 'Audit records unavailable due to error.' : 'No decisions found matching criteria.'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {filteredDecisions.map((dec) => {
              const isExpanded = expandedId === dec.id;
              return (
                <div
                  key={dec.id}
                  style={{
                    background: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    padding: '14px 18px',
                    cursor: 'pointer',
                    transition: 'border-color 0.2s ease',
                  }}
                  onClick={() => setExpandedId(isExpanded ? null : dec.id)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      <span className={`badge-action action-${dec.action}`}>
                        {dec.action.replace(/_/g, ' ')}
                      </span>
                      <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#f1f5f9' }}>
                        Ad: <code className="mono">{dec.advertisement_id}</code>
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                      <span>Policy: <strong>{dec.policy_version}</strong></span>
                      <span>Confidence: <strong style={{ color: '#cbd5e1' }}>{dec.confidence_level}</strong></span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Calendar size={13} />
                        <span>{new Date(dec.created_at).toLocaleTimeString()}</span>
                      </div>
                    </div>
                  </div>

                  <p style={{ fontSize: '0.85rem', color: '#cbd5e1', marginTop: '10px', marginLeft: '28px', lineHeight: 1.4 }}>
                    {dec.reason}
                  </p>

                  {/* Expanded JSON details */}
                  {isExpanded && (
                    <div
                      style={{
                        marginTop: '14px',
                        padding: '12px',
                        background: '#07090e',
                        border: '1px solid rgba(255, 255, 255, 0.06)',
                        borderRadius: '6px',
                        marginLeft: '28px',
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', fontSize: '0.72rem', color: '#818cf8' }}>
                        <Code size={13} />
                        <span>IMMUTABLE EVIDENCE SNAPSHOT (DECISION ID: {dec.id})</span>
                      </div>
                      <pre className="mono" style={{ fontSize: '0.72rem', color: '#94a3b8', overflowX: 'auto' }}>
                        {JSON.stringify(dec, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
