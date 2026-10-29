# Economic Evaluator Integrity and Shadow-Mode Readiness Audit Report

**Document Version:** 1.0.0  
**Audit Date:** October 28, 2026  
**Auditor:** Evaluation Engineering & Statistical Integrity Team  
**Evaluation Scope:** 190 Paired Simulation Runs (450 Total Advertisements)  
**Companion Artifacts:**  
- Independent Reconciliation Script: [`scratch/audit_step_4d9_reconciliation.py`](file:///d:/Developer/qualloop/scratch/audit_step_4d9_reconciliation.py)
- Audit Machine-Readable Results: [`scratch/step_4d9_audit_results.json`](file:///d:/Developer/qualloop/scratch/step_4d9_audit_results.json)
- Audit Test Suite: [`backend/tests/test_step_4d9_audit.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d9_audit.py)
- Evaluator Implementation: [`scratch/economic_evaluator.py`](file:///d:/Developer/qualloop/scratch/economic_evaluator.py)

---

## 1. Executive Summary & Audit Verdict

| Audit Domain | Verdict | Key Finding |
|---|---|---|
| **1. Mathematical Reconciliation** | **RECONCILED (with bug fix)** | Identified that Historical Phase paired analysis suffered from an ad ID collision across presets sharing seeds (370 unique IDs instead of 450). Replaced with composite key `(scenario_name, seed, creative_id)`, reconciling aggregate profit and paired difference sums to **₹0.00 error across all policies**. |
| **2. Decision-Time Isolation** | **VERIFIED & SECURE** | AST inspection and unit tests confirm `evaluate_ad_economic_viability` accepts zero ground truth and accesses no future timestamps. |
| **3. Statistical Calibration** | **EXPLORATORY (Not Calibrated)** | While parameter uncertainty ($\text{Beta}$ posteriors) is modeled, future lead arrivals and realization variance are projected deterministically. Formally classified as **exploratory**. |
| **4. Shadow-Mode Readiness** | **SAFE FOR READ-ONLY SHADOWING** | Defined schema and isolation safeguards. Shadow mode is safe to implement in log-only mode; live production actioning remains prohibited. |

---

## 2. Mathematical Profit Reconciliation ($N=450$ Ads)

### 2.1 Root Cause of Historical Phase Discrepancy
In Historical Phase, aggregate policy profit differences did not exactly match the paired per-ad difference sums:
- In `run_evaluation_step_4d8.py`, ads were stored in a dictionary keyed solely by `a["ad_id"]`.
- The simulation engine uses `_deterministic_id(rng)` initialized with `seed`. In the preset benchmark (10 seeds, 9 presets per seed = 90 runs), identical seeds (e.g. 26001) were reused across different presets.
- Consequently, the first ad of each preset with the same seed generated the exact same UUID, causing **80 ads to overwrite earlier entries**, reducing the paired sample from 450 to 370 ads.
- **Resolution:** Historical Phase introduces composite key `f"{scenario_name}_{seed}_{creative_id}"`. Every one of the 450 ads is distinct, and all paired sums reconcile to policy aggregate totals to ₹0.00.

### 2.2 Reconciled Policy Totals Across All 450 Ads

| Policy Identifier | Total Spend | Total QL | Portfolio CPQL | Net Profit ($V=300$) | Net Profit ($V=600$) | Net Profit ($V=1,200$) | Net Profit (Segmented) |
|---|---|---|---|---|---|---|---|
| **PROD_HEURISTIC_P10** | ₹2,161,125.00 | 5,175 | ₹417.61 | -₹608,625.00 | ₹943,875.00 | ₹4,048,875.00 | ₹1,369,675.00 |
| **PROD_HEURISTIC_P15** | ₹2,075,000.00 | 5,108 | ₹406.23 | -₹542,600.00 | ₹989,800.00 | ₹4,054,600.00 | ₹1,411,400.00 |
| **ECON_V300** | ₹1,963,125.00 | 5,055 | ₹388.35 | -₹446,625.00 | ₹1,069,875.00 | ₹4,102,875.00 | ₹1,485,575.00 |
| **ECON_V600** | ₹2,164,625.00 | 5,205 | ₹415.87 | -₹603,125.00 | ₹958,375.00 | ₹4,081,375.00 | ₹1,388,075.00 |
| **ECON_V1200** | ₹2,266,125.00 | 5,244 | ₹432.14 | -₹692,925.00 | ₹880,275.00 | ₹4,026,675.00 | ₹1,309,875.00 |
| **ECON_SEGMENTED** | ₹2,106,875.00 | 5,165 | ₹407.91 | -₹557,375.00 | ₹992,125.00 | ₹4,091,125.00 | ₹1,438,625.00 |

---

### 2.3 Reconciled Paired Differences vs Baseline (`PROD_HEURISTIC_P10`) on Full $N=450$

*(Formula: $\Delta \Pi_i = \Pi_{i, \text{cand}} - \Pi_{i, \text{base}}$; Verified identity: $\sum_{i=1}^{450} \Delta \Pi_i \equiv \Pi_{\text{cand}}^{\text{total}} - \Pi_{\text{base}}^{\text{total}}$)*

| Candidate Policy | Valuation Scenario | Candidate Profit | Baseline Profit | Reconciled Total Delta ($\sum \Delta \Pi$) | Reconciliation Error | Mean Delta / Ad ($\bar{\Delta}$) | SE ($\text{SE}$) | 95% Confidence Interval | Paired $t$-stat | $p$-value |
|---|---|---|---|---|---|---|---|---|---|---|
| **PROD_HEURISTIC_P15** | $V=300$ | -₹542,600 | -₹608,625 | +₹66,025.00 | **₹0.00** | +₹146.72 | ₹21.13 | [+₹105.31, +₹188.13] | 6.95 | $< 10^{-10}$ |
| | $V=600$ | ₹989,800 | ₹943,875 | +₹45,925.00 | **₹0.00** | +₹102.06 | ₹18.87 | [+₹65.06, +₹139.05] | 5.41 | $< 10^{-7}$ |
| | Segmented | ₹1,411,400 | ₹1,369,675 | +₹41,725.00 | **₹0.00** | +₹92.72 | ₹24.40 | [+₹44.90, +₹140.54] | 3.80 | $0.00016$ |
| **ECON_V300** | $V=300$ | -₹446,625 | -₹608,625 | **+₹162,000.00** | **₹0.00** | **+₹360.00** | ₹35.05 | **[+₹291.29, +₹428.71]** | **10.27** | **$< 10^{-15}$** |
| | $V=600$ | ₹1,069,875 | ₹943,875 | +₹126,000.00 | **₹0.00** | +₹280.00 | ₹32.16 | [+₹216.97, +₹343.03] | 8.71 | $< 10^{-15}$ |
| | Segmented | ₹1,485,575 | ₹1,369,675 | +₹115,900.00 | **₹0.00** | +₹257.56 | ₹37.26 | [+₹184.52, +₹330.59] | 6.91 | $< 10^{-10}$ |
| **ECON_V600** | $V=600$ | ₹958,375 | ₹943,875 | +₹14,500.00 | **₹0.00** | +₹32.22 | ₹27.20 | [-₹21.08, +₹85.53] | 1.18 | $0.23674$ |
| | Segmented | ₹1,388,075 | ₹1,369,675 | +₹18,400.00 | **₹0.00** | +₹40.89 | ₹36.25 | [-₹30.17, +₹111.95] | 1.13 | $0.26000$ |
| **ECON_V1200** | $V=1200$ | ₹4,026,675 | ₹4,048,875 | -₹22,200.00 | **₹0.00** | -₹49.33 | ₹37.66 | [-₹123.14, +₹24.47] | -1.31 | $0.19082$ |
| | Segmented | ₹1,309,875 | ₹1,369,675 | -₹59,800.00 | **₹0.00** | -₹132.89 | ₹39.79 | [-₹210.88, -₹54.90] | -3.34 | $0.00091$ |
| **ECON_SEGMENTED** | $V=300$ | -₹557,375 | -₹608,625 | +₹51,250.00 | **₹0.00** | +₹113.89 | ₹32.75 | [+₹49.69, +₹178.09] | 3.48 | $0.00056$ |
| | $V=600$ | ₹992,125 | ₹943,875 | +₹48,250.00 | **₹0.00** | +₹107.22 | ₹30.81 | [+₹46.84, +₹167.61] | 3.48 | $0.00055$ |
| | Segmented | ₹1,438,625 | ₹1,369,675 | **+₹68,950.00** | **₹0.00** | **+₹153.22** | ₹38.78 | **[+₹77.21, +₹229.24]** | **3.95** | **$0.00009$** |

*All standard errors and confidence intervals use $N=450$ paired ad evaluations.*

---

## 3. Decision-Time Information Audit

Every input consumed by [`evaluate_ad_economic_viability`](file:///d:/Developer/qualloop/scratch/economic_evaluator.py#L45) was traced to verify provenance:

| Input Field | Source / Expression | Classification | Leakage Check |
|---|---|---|---|
| `snapshot.n_leads` | Cumulative leads created $\le t_{\text{checkpoint}}$ | **Historical Observation** | PASS (bounded by $t_{\text{cp}}$) |
| `snapshot.n_contacts` | Cumulative contacts reached $\le t_{\text{checkpoint}}$ | **Historical Observation** | PASS (bounded by $t_{\text{cp}}$) |
| `snapshot.n_mature_contacts` | Contacts with window $\ge \tau_{\text{qual}}$ resolved $\le t_{\text{checkpoint}}$ | **Historical Observation** | PASS (bounded by $t_{\text{cp}}$) |
| `snapshot.k_qualified` | Leads qualified $\le t_{\text{checkpoint}}$ | **Historical Observation** | PASS (bounded by $t_{\text{cp}}$) |
| `cumulative_spend` | Platform media spend accrued $\le t_{\text{checkpoint}}$ | **Historical Observation** | PASS (bounded by $t_{\text{cp}}$) |
| `current_day` | Checkpoint evaluation day (e.g. 3, 7, 14, 21) | **Historical Observation** | PASS |
| `params.decision_horizon_days` | Forward decision window $\Delta t = 7.0$ days | **Explicit Business Assumption** | PASS (configured param) |
| `params.lead_value` | $V_{\text{QL}}$ (Rs 300, 600, 1200) | **Explicit Business Assumption** | PASS (configured param) |
| `params.cost_per_lead` | CRM lead intake cost ($c_{\text{lead}} = 0$) | **Explicit Business Assumption** | PASS (configured param) |
| `params.cost_per_call` | Telephony dialer cost ($c_{\text{call}} = 0$) | **Explicit Business Assumption** | PASS (configured param) |
| `params.min_mature_contacts` | Statistical sample size gate ($N_{\text{min}} = 20$) | **Explicit Business Assumption** | PASS (configured param) |
| `params.min_maturity_fraction` | Evidence maturity gate ($\tau_{\text{mat}} = 0.60$) | **Explicit Business Assumption** | PASS (configured param) |
| `params.confidence_level` | Pause credible threshold ($1 - \alpha = 0.90$) | **Explicit Business Assumption** | PASS (configured param) |
| `true_intent`, `true_reachability` | Simulation ground-truth attributes | **Ground Truth** | **NEVER ACCESSED** |
| Post-checkpoint outcomes | Leads, calls, qualifications after $t_{\text{cp}}$ | **Future Outcome** | **NEVER ACCESSED** |

**Conclusion:** Strict decision-time isolation is verified.

---

## 4. Statistical Uncertainty and Calibration Audit

### 4.1 Funnel Representation
- **Reachability Posterior:** $r \sim \text{Beta}(1 + C, 1 + (L_{\text{mat}} - C))$.
- **Qualification Posterior:** $q \sim \text{Beta}(1 + QL, 4 + (C_{\text{mat}} - QL))$.
- **Joint Uncertainty:** Monte Carlo sampling (4,000 draws) propagates the joint product $r \cdot q$ to estimate qualified lead arrivals $\Delta QL = \Delta L \cdot r \cdot q$.

### 4.2 Calibration Defect: Why Output is Labeled "Exploratory"
An empirical calibration check was performed across 132 unpaused ads active at Day 14 under `ECON_V600`:
- **Mean predicted probability of being profitable over the next 14 days:** $65.57\%$
- **Actual empirical fraction of ads that were profitable:** $2.27\%$

#### Why does this gap occur?
1. **Deterministic Volume Projection:** The evaluator projects future arrivals as $\Delta L = \bar{\lambda} \cdot \Delta t$, ignoring Poisson realization variance $\text{Var}(L) = \lambda \Delta t$.
2. **Binomial Realization Noise Ignored:** The model simulates parameter uncertainty ($r, q$), but treats the future count as continuous ($\Delta L \cdot r \cdot q$) rather than drawing Binomial realizations $\text{Binomial}(\Delta L, r \cdot q)$.
3. **CPL Volatility:** CPL is assumed fixed at historical average, ignoring bid auctions and creative fatigue.

**Audit Mandate:** Because predictive realization variance is omitted, `probability_profitable` reflects parameter confidence given expected volume, NOT calibrated empirical probability. The output must be explicitly labeled:
$$\textbf{CALIBRATION\_STATUS = EXPLORATORY\_NOT\_CALIBRATED}$$

---

## 5. Shadow-Mode Feasibility and Architectural Contracts

Shadow-mode evaluation is **safe to implement** provided it operates in a non-actioning, read-only capacity.

### 5.1 Telemetry Contract for Shadow Logging
The shadow evaluator must emit a structured event to `audit_trail` on each evaluation cycle:

```json
{
  "event_type": "SHADOW_ECONOMIC_DECISION_LOGGED",
  "decision_timestamp": "2026-10-28T12:00:00Z",
  "advertisement_id": "ad-5829104",
  "campaign_id": "cmp-9812401",
  "evaluator_version": "economic_evaluator_v1_prototype",
  "inputs_snapshot": {
    "cumulative_spend": 2450.00,
    "current_day": 14.0,
    "n_leads": 48,
    "n_contacts": 28,
    "n_mature_contacts": 24,
    "k_qualified": 2,
    "maturity_fraction_contact": 0.85,
    "reachability_mean": 0.583,
    "qualification_mean": 0.103
  },
  "business_assumptions": {
    "lead_value": 600.00,
    "provenance": "MANUAL_CLIENT_CONFIGURATION_TIER_SMB",
    "decision_horizon_days": 7.0,
    "confidence_level": 0.90
  },
  "shadow_decision": {
    "action": "PAUSE",
    "expected_incremental_spend": 1225.00,
    "expected_incremental_ql": 1.25,
    "expected_incremental_profit": -475.00,
    "profit_ci_90": [-850.00, -120.00],
    "probability_profitable": 0.042,
    "calibration_status": "EXPLORATORY_NOT_CALIBRATED",
    "reason": "Exploratory model projection indicates projected CPQL (Rs 980.00) exceeds breakeven (Rs 600.00). Exploratory model probability of profitability: 4.2% (uncalibrated estimate)."
  },
  "production_action_taken": "CONTINUE",
  "is_shadow_only": true
}
```

### 5.2 Mandatory Safeguards
1. **No Outbound Mutation:** The shadow evaluator module must have no dependency or client binding to Meta Marketing API, Google Ads API, or any ad-mutation worker.
2. **Read-Only Database Permissions:** Shadow worker uses a read-only replica connection string.
3. **Strict Decoupling from API Responses:** The public `/api/v1/decisions` endpoints must continue serving solely the output of `evaluate_campaign` (heuristic policy).
4. **Audit Trail Isolation:** Shadow events must be tagged `is_shadow_only = true` so compliance queries and client dashboards do not display shadow pauses as enacted decisions.

---

## 6. Audit Verdict and Next Action

### Verdict:
1. **Profit Totals Reconciled:** Verified to ₹0.00 error across all 450 ads ($N=450$).
2. **Decision-Time Isolation:** Fully verified and tested.
3. **Statistical Uncertainty:** Formally designated as **exploratory** due to unmodeled Poisson realization variance.
4. **Shadow Mode Readiness:** **Approved for read-only shadow instrumentation.**

### Remaining Blockers:
- **Client Lead Valuation Interface:** QualLoop currently lacks customer-facing UI/API to capture and audit $V_{\text{QL}}$ provenance.
- **Realization-Noise Propagation:** Poisson and negative-binomial uncertainty must be added to Monte Carlo sampling before removing the "exploratory" label.

### Next Highest-ROI Action:
Implement the read-only shadow logging schema in `backend/audit/trail.py` and capture 30 days of real client ad trajectories without modifying production decision behavior.
