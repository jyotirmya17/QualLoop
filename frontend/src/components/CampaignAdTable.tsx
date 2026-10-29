import React, { useState } from 'react';
import { ExternalLink, Filter, HelpCircle, AlertTriangle } from 'lucide-react';
import { CampaignSummary, AdAnalysis } from '../types/api';

interface CampaignAdTableProps {
  campaigns: CampaignSummary[];
  onSelectAd: (adAnalysis: AdAnalysis) => void;
}

export const CampaignAdTable: React.FC<CampaignAdTableProps> = ({ campaigns, onSelectAd }) => {
  const [filterAction, setFilterAction] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Flatten all ads across campaigns with their campaign name
  const allAds: Array<{ ad: AdAnalysis; campaignName: string }> = [];
  campaigns.forEach((camp) => {
    camp.ads.forEach((adAnalysis) => {
      allAds.push({ ad: adAnalysis, campaignName: camp.campaign_name });
    });
  });

  // Filter
  const filtered = allAds.filter(({ ad, campaignName }) => {
    if (filterAction !== 'all' && ad.decision.action !== filterAction) {
      return false;
    }
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      return (
        ad.advertisement.creative_id.toLowerCase().includes(term) ||
        campaignName.toLowerCase().includes(term) ||
        ad.decision.reason.toLowerCase().includes(term)
      );
    }
    return true;
  });

  const formatActionName = (action: string) => {
    return action.replace(/_/g, ' ');
  };

  return (
    <div className="glass-card" style={{ padding: '20px' }}>
      {/* Table Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
          marginBottom: '20px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h3 style={{ fontSize: '1.1rem' }}>Creatives & Decision Engine Evidence</h3>
          <span
            style={{
              fontSize: '0.75rem',
              background: 'rgba(255, 255, 255, 0.08)',
              padding: '2px 8px',
              borderRadius: '999px',
              color: 'var(--text-muted)',
            }}
          >
            {filtered.length} of {allAds.length} Ads
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Filter size={14} color="var(--text-dim)" />
            <select
              className="form-select"
              style={{ padding: '6px 12px', fontSize: '0.8rem' }}
              value={filterAction}
              onChange={(e) => setFilterAction(e.target.value)}
            >
              <option value="all">All Recommendations</option>
              <option value="continue_monitoring">Continue Monitoring</option>
              <option value="collect_more_data">Collect More Data</option>
              <option value="investigate_low_reachability">Investigate Low Reachability</option>
              <option value="refresh_creative">Refresh Creative</option>
              <option value="consider_pause">Consider Pause</option>
              <option value="consider_reallocate">Consider Reallocate</option>
              <option value="flag_insufficient_evidence">Insufficient Evidence</option>
            </select>
          </div>

          <input
            type="text"
            className="form-input"
            style={{ padding: '6px 12px', fontSize: '0.8rem', width: '200px' }}
            placeholder="Search creative ID / reason..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Table Container */}
      <div className="data-table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Creative Identifier</th>
              <th>Spend / Volume</th>
              <th>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span>Reachability Rate (90% CI)</span>
                  <span title="Beta-Binomial posterior credible interval of lead contact rate" style={{ display: 'inline-flex', cursor: 'help' }}>
                    <HelpCircle size={12} />
                  </span>
                </div>
              </th>
              <th>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span>Qualification Rate (90% CI)</span>
                  <span title="Beta-Binomial posterior of buyer qualification among contacted leads" style={{ display: 'inline-flex', cursor: 'help' }}>
                    <HelpCircle size={12} />
                  </span>
                </div>
              </th>
              <th>Est. Qualified Leads (EQL)</th>
              <th>Est. CPQL (Truncated Mean)</th>
              <th>Cohort Maturity</th>
              <th>Recommendation</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ textAlign: 'center', padding: '36px', color: 'var(--text-dim)' }}>
                  No advertisements match the selected filter criteria.
                </td>
              </tr>
            ) : (
              filtered.map(({ ad, campaignName }) => {
                const est = ad.estimate;
                const dec = ad.decision;
                const adv = ad.advertisement;

                const reachLow = Math.max(0, est.reachability_ci_low * 100);
                const reachHigh = Math.min(100, est.reachability_ci_high * 100);
                const reachMean = est.reachability_mean * 100;

                const qualLow = Math.max(0, est.qualification_ci_low * 100);
                const qualHigh = Math.min(100, est.qualification_ci_high * 100);
                const qualMean = est.qualification_mean * 100;

                const isSmallCohort = est.n_mature_leads < 30;

                return (
                  <tr key={adv.id}>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ fontWeight: 600, color: '#f8fafc' }}>
                          {adv.creative_id}
                        </span>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                          {campaignName}
                        </span>
                      </div>
                    </td>

                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ fontWeight: 600 }}>₹{adv.spend.toFixed(0)}</span>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                          {est.n_leads} leads &bull; {adv.clicks} clicks
                        </span>
                      </div>
                    </td>

                    {/* Reachability CI bar */}
                    <td>
                      <div className="ci-bar-wrapper">
                        <div className="ci-bar-labels">
                          <span>{reachMean.toFixed(1)}%</span>
                          <span>[{reachLow.toFixed(0)}%, {reachHigh.toFixed(0)}%]</span>
                        </div>
                        <div className="ci-bar-track">
                          <div
                            className="ci-bar-range"
                            style={{
                              left: `${reachLow}%`,
                              width: `${Math.max(2, reachHigh - reachLow)}%`,
                              background: 'rgba(6, 182, 212, 0.35)',
                            }}
                          />
                          <div
                            className="ci-bar-mean"
                            style={{
                              left: `${reachMean}%`,
                              background: '#06b6d4',
                            }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Qualification CI bar */}
                    <td>
                      <div className="ci-bar-wrapper">
                        <div className="ci-bar-labels">
                          <span style={{ color: qualMean < 10 ? '#fb7185' : '#34d399' }}>
                            {qualMean.toFixed(1)}%
                          </span>
                          <span>[{qualLow.toFixed(0)}%, {qualHigh.toFixed(0)}%]</span>
                        </div>
                        <div className="ci-bar-track">
                          <div
                            className="ci-bar-range"
                            style={{
                              left: `${qualLow}%`,
                              width: `${Math.max(2, qualHigh - qualLow)}%`,
                              background: qualMean < 10 ? 'rgba(244, 63, 94, 0.35)' : 'rgba(16, 185, 129, 0.35)',
                            }}
                          />
                          <div
                            className="ci-bar-mean"
                            style={{
                              left: `${qualMean}%`,
                              background: qualMean < 10 ? '#f43f5e' : '#10b981',
                            }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* EQL */}
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ fontWeight: 700, color: '#e2e8f0' }}>
                          {est.eql_mean.toFixed(1)}
                        </span>
                        <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                          [{est.eql_ci_low.toFixed(1)}, {est.eql_ci_high.toFixed(1)}]
                        </span>
                      </div>
                    </td>

                    {/* CPQL */}
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        {est.cpql_unstable || est.cpql_mean === null ? (
                          <span style={{ color: '#f59e0b', fontSize: '0.75rem', fontWeight: 600 }}>
                            Unstable
                          </span>
                        ) : (
                          <>
                            <span style={{ fontWeight: 600 }}>₹{est.cpql_mean.toFixed(0)}</span>
                            <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                              [{est.cpql_ci_low?.toFixed(0)}, {est.cpql_ci_high?.toFixed(0)}]
                            </span>
                          </>
                        )}
                      </div>
                    </td>

                    {/* Maturity */}
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {isSmallCohort && (
                          <span title="Small sample (<30 mature leads)" style={{ display: 'inline-flex', cursor: 'help' }}>
                            <AlertTriangle size={13} color="#f59e0b" />
                          </span>
                        )}
                        <span style={{ fontSize: '0.8rem', color: isSmallCohort ? '#fde68a' : 'var(--text-main)' }}>
                          {(est.maturity_fraction_qualification * 100).toFixed(0)}%
                        </span>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                          ({est.n_mature_leads}/{est.n_leads})
                        </span>
                      </div>
                    </td>

                    {/* Action badge */}
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
                        <span className={`badge-action action-${dec.action}`}>
                          {formatActionName(dec.action)}
                        </span>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>
                          Confidence: <strong style={{ color: '#cbd5e1' }}>{dec.confidence_level}</strong>
                        </span>
                      </div>
                    </td>

                    {/* Inspect button */}
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '5px 10px', fontSize: '0.75rem' }}
                        onClick={() => onSelectAd(ad)}
                      >
                        <span>Inspect</span>
                        <ExternalLink size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
