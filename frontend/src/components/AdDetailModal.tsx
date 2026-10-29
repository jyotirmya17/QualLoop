import React from 'react';
import {
  X,
  PhoneCall,
  Award,
  DollarSign,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { AdAnalysis } from '../types/api';

interface AdDetailModalProps {
  adAnalysis: AdAnalysis | null;
  onClose: () => void;
}

export const AdDetailModal: React.FC<AdDetailModalProps> = ({ adAnalysis, onClose }) => {
  if (!adAnalysis) return null;

  const { advertisement: adv, estimate: est, decision: dec } = adAnalysis;

  const reachLow = (est.reachability_ci_low * 100).toFixed(1);
  const reachHigh = (est.reachability_ci_high * 100).toFixed(1);
  const reachMean = (est.reachability_mean * 100).toFixed(1);

  const qualLow = (est.qualification_ci_low * 100).toFixed(1);
  const qualHigh = (est.qualification_ci_high * 100).toFixed(1);
  const qualMean = (est.qualification_mean * 100).toFixed(1);

  const formatAction = (a: string) => a.replace(/_/g, ' ').toUpperCase();

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content animate-fade-in"
        style={{ maxWidth: '780px' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'white',
              }}
            >
              <Award size={22} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h2 style={{ fontSize: '1.3rem' }}>{adv.creative_id}</h2>
                <span className={`badge-action action-${dec.action}`}>
                  {formatAction(dec.action)}
                </span>
              </div>
              <p className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                <span>Ad ID: {adv.id}</span>
                <span>&bull;</span>
                <span>Decision ID: <strong style={{ color: dec.is_persisted ? '#818cf8' : '#94a3b8' }}>{dec.is_persisted ? dec.id : `${dec.id} (Preview)`}</strong></span>
                <span
                  style={{
                    fontSize: '0.68rem',
                    padding: '1px 6px',
                    borderRadius: '4px',
                    fontWeight: 600,
                    background: dec.is_persisted ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                    color: dec.is_persisted ? '#34d399' : '#fbbf24',
                    border: dec.is_persisted ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid rgba(245, 158, 11, 0.3)',
                  }}
                >
                  {dec.is_persisted ? 'AUDITED' : 'PREVIEW ONLY — NOT PERSISTED'}
                </span>
                <span>&bull;</span>
                <span>Policy {dec.policy_version}</span>
              </p>
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Warning Banner */}
        <div
          style={{
            background: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid rgba(245, 158, 11, 0.25)',
            borderRadius: '8px',
            padding: '10px 14px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '0.78rem',
            color: '#fde68a',
          }}
        >
          <AlertTriangle size={15} color="#f59e0b" />
          <span>⚠ Simulated Data & Isolated Bayesian Model: Pending leads are excluded from qualification denominator.</span>
        </div>

        {/* Core Decision & Evidence */}
        <div
          style={{
            background: 'rgba(255, 255, 255, 0.02)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '12px',
            padding: '18px 20px',
            marginBottom: '24px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#818cf8', textTransform: 'uppercase' }}>
              Decision Engine Justification
            </span>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
              Confidence Level: <strong style={{ color: '#e2e8f0' }}>{dec.confidence_level.toUpperCase()}</strong>
            </span>
          </div>
          <p style={{ fontSize: '0.92rem', color: '#f1f5f9', lineHeight: 1.5, marginBottom: '12px' }}>
            {dec.reason}
          </p>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {dec.requires_human_approval && (
              <span style={{ fontSize: '0.72rem', background: 'rgba(236, 72, 153, 0.15)', color: '#f472b6', padding: '3px 8px', borderRadius: '4px', border: '1px solid rgba(236, 72, 153, 0.3)' }}>
                Requires Human Sign-off
              </span>
            )}
            <span style={{ fontSize: '0.72rem', background: 'rgba(16, 185, 129, 0.15)', color: '#34d399', padding: '3px 8px', borderRadius: '4px', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
              Approval: {dec.approval_status}
            </span>
            <span style={{ fontSize: '0.72rem', background: 'rgba(99, 102, 241, 0.15)', color: '#a5b4fc', padding: '3px 8px', borderRadius: '4px', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
              Spend: ${adv.spend.toFixed(0)}
            </span>
          </div>
        </div>

        {/* Statistical Decomposition Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          {/* 1. Reachability Card */}
          <div style={{ background: 'rgba(6, 182, 212, 0.05)', border: '1px solid rgba(6, 182, 212, 0.2)', borderRadius: '12px', padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <PhoneCall size={16} color="#06b6d4" />
              <h4 style={{ fontSize: '0.9rem', color: '#67e8f9' }}>Contactability (Reachability)</h4>
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#f8fafc', marginBottom: '4px' }}>
              {reachMean}%
            </div>
            <div className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '12px' }}>
              90% Credible Interval: [{reachLow}%, {reachHigh}%]
            </div>

            <div style={{ fontSize: '0.78rem', color: 'var(--text-dim)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div>&bull; Observed contacts: <strong style={{ color: '#e2e8f0' }}>{est.n_contacts}</strong> / {est.n_mature_leads} mature leads</div>
              <div>&bull; Total leads cohort: {est.n_leads} ({(est.maturity_fraction_contact * 100).toFixed(0)}% mature)</div>
              <div>&bull; Prior: Beta(1, 1) flat uninformative</div>
              <div>&bull; Evidence sufficient: {est.evidence_sufficient_reachability ? '✓ Yes' : '✗ Need more data'}</div>
            </div>
          </div>

          {/* 2. Qualification Card */}
          <div style={{ background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '12px', padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <CheckCircle2 size={16} color="#10b981" />
              <h4 style={{ fontSize: '0.9rem', color: '#6ee7b7' }}>Qualification Intent</h4>
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, color: '#f8fafc', marginBottom: '4px' }}>
              {qualMean}%
            </div>
            <div className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '12px' }}>
              90% Credible Interval: [{qualLow}%, {qualHigh}%]
            </div>

            <div style={{ fontSize: '0.78rem', color: 'var(--text-dim)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div>&bull; Verified buyers: <strong style={{ color: '#e2e8f0' }}>{est.k_qualified}</strong> / {est.n_mature_contacts} mature contacts</div>
              <div>&bull; Denominator excludes unreachable: <strong>True</strong></div>
              <div>&bull; Prior: Beta(1, 4) informative (exp. ~20%)</div>
              <div>&bull; Evidence sufficient: {est.evidence_sufficient_qualification ? '✓ Yes' : '✗ Immature sample'}</div>
            </div>
          </div>
        </div>

        {/* 3. Economic Card: CPQL & EQL */}
        <div
          style={{
            background: 'rgba(99, 102, 241, 0.05)',
            border: '1px solid rgba(99, 102, 241, 0.2)',
            borderRadius: '12px',
            padding: '16px 20px',
            marginBottom: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <DollarSign size={16} color="#818cf8" />
            <h4 style={{ fontSize: '0.9rem', color: '#c7d2fe' }}>Economic Quantification & CPQL Monte Carlo</h4>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Estimated Qualified Leads (EQL):</span>
              <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#f8fafc' }}>
                {est.eql_mean.toFixed(1)}
              </div>
              <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                90% CI: [{est.eql_ci_low.toFixed(1)}, {est.eql_ci_high.toFixed(1)}]
              </span>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Cost Per Qualified Lead (CPQL, Truncated Mean):</span>
              <div style={{ fontSize: '1.3rem', fontWeight: 700, color: est.cpql_unstable ? '#f59e0b' : '#34d399' }}>
                {est.cpql_unstable || est.cpql_mean === null ? 'Unstable' : `$${est.cpql_mean.toFixed(0)}`}
              </div>
              <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                {est.cpql_unstable
                  ? `Zero-EQL draw fraction: ${(est.zero_eql_fraction * 100).toFixed(0)}%`
                  : `90% CI: [$${est.cpql_ci_low?.toFixed(0)}, $${est.cpql_ci_high?.toFixed(0)}]`}
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
          <button className="btn btn-primary" onClick={onClose}>
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
