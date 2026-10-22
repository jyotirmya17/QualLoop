export type DecisionAction =
  | 'collect_more_data'
  | 'continue_monitoring'
  | 'investigate_low_reachability'
  | 'refresh_creative'
  | 'pause_ad'
  | 'consider_pause'
  | 'reallocate_budget'
  | 'consider_reallocate'
  | 'shift_spend'
  | 'raise_budget'
  | 'launch_ad'
  | 'flag_insufficient_evidence'
  | 'flag_abnormal_change';

export type DecisionTier = 'gated' | 'within_guardrails' | 'autonomous';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'not_required';

export interface SimulationRun {
  id: string;
  scenario_name: string;
  seed: number;
  started_at: string;
  completed_at: string | null;
  n_campaigns: number;
  n_ads: number;
  n_leads: number;
}

export interface Advertisement {
  id: string;
  ad_set_id: string;
  creative_id: string;
  spend: number;
  impressions: number;
  clicks: number;
}

export interface EstimateSnapshot {
  id: string;
  advertisement_id: string;
  computed_at: string;
  estimator_version: string;
  n_leads: number;
  n_mature_leads: number;
  n_contacts: number;
  n_mature_contacts: number;
  k_qualified: number;
  maturity_fraction_contact: number;
  maturity_fraction_qualification: number;
  reachability_mean: number;
  reachability_ci_low: number;
  reachability_ci_high: number;
  qualification_mean: number;
  qualification_ci_low: number;
  qualification_ci_high: number;
  eql_mean: number;
  eql_ci_low: number;
  eql_ci_high: number;
  cpql_mean: number | null;
  cpql_ci_low: number | null;
  cpql_ci_high: number | null;
  cpql_unstable: boolean;
  evidence_sufficient_reachability: boolean;
  evidence_sufficient_qualification: boolean;
  zero_eql_fraction: number;
}

export interface Decision {
  id: string;
  advertisement_id: string;
  estimate_snapshot_id: string;
  policy_version: string;
  action: DecisionAction;
  reason: string;
  supporting_metrics: Record<string, any>;
  confidence_level: 'high' | 'medium' | 'low';
  tier?: DecisionTier;
  auto_applied?: boolean;
  requires_human_approval: boolean;
  approval_status: ApprovalStatus;
  created_at: string;
}

export interface AdAnalysis {
  advertisement: Advertisement;
  estimate: EstimateSnapshot;
  decision: Decision;
  simulated_data_warning: string;
}

export interface CampaignSummary {
  campaign_id: string;
  campaign_name: string;
  total_spend: number;
  n_ads: number;
  ads: AdAnalysis[];
}

export interface ScenarioBreakdown {
  scenario_name: string;
  n_simulations: number;
  n_ads: number;
  qualloop_fppr: number;
  baseline_fppr: number;
  qualloop_fndr: number;
  baseline_fndr: number;
}

export interface BenchmarkReport {
  run_metadata: {
    n_simulations: number;
    n_ads_evaluated: number;
    n_good_ads: number;
    n_poor_ads: number;
    seed_file: string;
    qualloop_policy_version: string;
    baseline_description: string;
    executed_at: string;
  };
  aggregate_metrics: {
    qualloop: {
      fppr_mean: number;
      fppr_ci: [number, number];
      fndr_mean: number;
      fndr_ci: [number, number];
      ier_mean: number;
      qlus: number;
      total_spend: number;
      total_qualified_leads_preserved: number;
    };
    baseline: {
      fppr_mean: number;
      fppr_ci: [number, number];
      fndr_mean: number;
      fndr_ci: [number, number];
      ier_mean: number;
      qlus: number;
      total_spend: number;
      total_qualified_leads_preserved: number;
    };
  };
  per_scenario_breakdown: ScenarioBreakdown[];
  cases_where_qualloop_performed_worse: Array<{
    run_id: string;
    scenario: string;
    seed: number;
    creative_id: string;
    is_good_ad: boolean;
    is_poor_ad: boolean;
    gt_intent_mean: number;
    qualloop_action: string;
    baseline_action: string;
    qualloop_reason: string;
    explanation: string;
  }>;
}

export interface HealthStatus {
  service: string;
  version: string;
  status: string;
  simulated_data_only: boolean;
  warning: string;
  timestamp: string;
  docs: string;
}
