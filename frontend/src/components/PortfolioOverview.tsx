import React from 'react';
import { DollarSign, Users, Award, PhoneCall, TrendingUp, AlertCircle, Clock, CheckCircle2 } from 'lucide-react';
import { CampaignSummary } from '../types/api';

interface PortfolioOverviewProps {
  campaigns: CampaignSummary[];
  scenarioName?: string;
  seed?: number;
  onEvaluate?: () => void;
  isEvaluating?: boolean;
}

export const PortfolioOverview: React.FC<PortfolioOverviewProps> = ({
  campaigns,
  scenarioName,
  seed,
  onEvaluate,
  isEvaluating,
}) => {
  // Aggregate stats across campaigns and ads
  let totalSpend = 0;
  let totalImpressions = 0;
  let totalClicks = 0;
  let totalLeads = 0;
  let totalMatureLeads = 0;
  let totalContacts = 0;
  let totalMatureContacts = 0;
  let totalQualified = 0;
  let totalEQL = 0;
  let totalEQLlow = 0;
  let totalEQLhigh = 0;
  let adCount = 0;

  campaigns.forEach((camp) => {
    totalSpend += camp.total_spend;
    camp.ads.forEach((ad) => {
      adCount++;
      totalImpressions += ad.advertisement.impressions;
      totalClicks += ad.advertisement.clicks;
      totalLeads += ad.estimate.n_leads;
      totalMatureLeads += ad.estimate.n_mature_leads;
      totalContacts += ad.estimate.n_contacts;
      totalMatureContacts += ad.estimate.n_mature_contacts;
      totalQualified += ad.estimate.k_qualified;
      totalEQL += ad.estimate.eql_mean;
      totalEQLlow += ad.estimate.eql_ci_low;
      totalEQLhigh += ad.estimate.eql_ci_high;
    });
  });

  const avgContactRate = totalMatureLeads > 0 ? (totalContacts / totalMatureLeads) : 0;
  const avgQualRate = totalMatureContacts > 0 ? (totalQualified / totalMatureContacts) : 0;
  const portfolioCPQL = totalEQL > 0 ? (totalSpend / totalEQL) : null;

  const isSmallSample = totalMatureLeads < 30;
  const maturityPct = totalLeads > 0 ? ((totalMatureLeads / totalLeads) * 100) : 100;
  const isMaturityLow = maturityPct < 60;

  return (
    <div style={{ marginBottom: '28px' }}>
      {/* Portfolio Info Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
        }}
      >
        <div>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700 }}>Portfolio Performance Overview</h2>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Active Scenario: <strong style={{ color: '#c7d2fe' }}>{scenarioName || 'N/A'}</strong> (Seed: {seed}) | {campaigns.length} Campaigns, {adCount} Creatives
          </p>
        </div>

        {/* Dynamic Warning Badges and Evaluate Action */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {onEvaluate && (
            <button
              className="btn btn-secondary"
              style={{ padding: '5px 12px', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '6px' }}
              onClick={onEvaluate}
              disabled={isEvaluating}
              title="Explicitly evaluate decisions and persist to immutable audit ledger"
            >
              <CheckCircle2 size={13} color="#10b981" />
              <span>{isEvaluating ? 'Evaluating...' : 'Evaluate & Persist'}</span>
            </button>
          )}
          {isSmallSample && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(245, 158, 11, 0.15)',
                border: '1px solid rgba(245, 158, 11, 0.4)',
                color: '#fbbf24',
                fontSize: '0.75rem',
                fontWeight: 600,
              }}
            >
              <AlertCircle size={14} />
              <span>Small Sample Warning (n &lt; 30)</span>
            </div>
          )}
          {isMaturityLow && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(6, 182, 212, 0.15)',
                border: '1px solid rgba(6, 182, 212, 0.4)',
                color: '#22d3ee',
                fontSize: '0.75rem',
                fontWeight: 600,
              }}
            >
              <Clock size={14} />
              <span>Cohort Immature ({maturityPct.toFixed(0)}% mature)</span>
            </div>
          )}
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">
            <span>Total Spend</span>
            <DollarSign size={16} color="#6366f1" />
          </div>
          <div className="kpi-value">₹{totalSpend.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</div>
          <div className="kpi-sub">{totalImpressions.toLocaleString()} imp &bull; {totalClicks.toLocaleString()} clicks</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            <span>Leads Generated</span>
            <Users size={16} color="#8b5cf6" />
          </div>
          <div className="kpi-value">{totalLeads}</div>
          <div className="kpi-sub">
            <strong style={{ color: '#cbd5e1' }}>{totalMatureLeads}</strong> mature ({maturityPct.toFixed(0)}%)
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            <span>Est. Qualified Leads (EQL)</span>
            <Award size={16} color="#10b981" />
          </div>
          <div className="kpi-value" style={{ color: '#34d399' }}>
            {totalEQL.toFixed(1)}
          </div>
          <div className="kpi-sub mono">
            90% CI: [{totalEQLlow.toFixed(1)}, {totalEQLhigh.toFixed(1)}]
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            <span>Reachability Rate</span>
            <PhoneCall size={16} color="#06b6d4" />
          </div>
          <div className="kpi-value">
            {(avgContactRate * 100).toFixed(1)}%
          </div>
          <div className="kpi-sub">
            {totalContacts} contacted of {totalMatureLeads} mature
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            <span>Contacted Qual. Rate</span>
            <TrendingUp size={16} color="#ec4899" />
          </div>
          <div className="kpi-value">
            {(avgQualRate * 100).toFixed(1)}%
          </div>
          <div className="kpi-sub">
            {totalQualified} qualified of {totalMatureContacts} contacts
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            <span>Portfolio CPQL</span>
            <DollarSign size={16} color="#f59e0b" />
          </div>
          <div className="kpi-value" style={{ color: portfolioCPQL ? '#fde68a' : 'var(--text-dim)' }}>
            {portfolioCPQL ? `₹${portfolioCPQL.toFixed(0)}` : 'Unstable'}
          </div>
          <div className="kpi-sub">
            {portfolioCPQL ? 'Cost per verified buyer' : 'Zero or near-zero qualified leads'}
          </div>
        </div>
      </div>
    </div>
  );
};
