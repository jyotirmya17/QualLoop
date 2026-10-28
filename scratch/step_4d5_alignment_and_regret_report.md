# Step 4D.5 — Benchmark Semantics Alignment & Economic Regret Report

**Role:** Skeptical ML Evaluation Engineer  
**Date:** 2026-10-28  
**Audit Scope:** Evaluation methodology audit. No production decision rules, defaults, migrations, or runtime behaviors modified; no git commits created.  
**Preserved Artifacts:**  
- Runner: [`scratch/run_evaluation_step_4d5.py`](file:///d:/Developer/qualloop/scratch/run_evaluation_step_4d5.py)
- Raw Results: [`scratch/step_4d5_aligned_evaluation.json`](file:///d:/Developer/qualloop/scratch/step_4d5_aligned_evaluation.json)
- Summary Script: [`scratch/print_4d5_summary.py`](file:///d:/Developer/qualloop/scratch/print_4d5_summary.py)
- Regression Tests: [`backend/tests/test_step_4d5_semantics.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d5_semantics.py)
- Report: [`scratch/step_4d5_alignment_and_regret_report.md`](file:///d:/Developer/qualloop/scratch/step_4d5_alignment_and_regret_report.md)

---

## 1. Threshold & Metric Dependency Map

Our comprehensive code trace across `backend/` identified multiple disconnected threshold definitions and disparate labeling conventions:

| Component / Parameter | Source File & Symbol | Configurable? | Effective Value | Semantic Role in QualLoop |
|---|---|---|---|---|
| **Production Decision Threshold** | [`backend/decision_engine/engine.py:36`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L36) `low_qualification_upper_bound` | Yes (`DecisionPolicy`) | **`0.10` (10%)** | Evaluated in Rule 6 (`engine.py:236`): Triggers `PAUSE_AD` (or `CONSIDER_PAUSE`) when Bayesian upper bound $\theta_{\text{high}} < 0.10$. Represents production viability standard. |
| **Benchmark Ground-Truth Hurdle** | [`backend/benchmark/robustness.py:36,51`](file:///d:/Developer/qualloop/backend/benchmark/robustness.py#L36) `hurdle` | Parametric | **`0.15` (15%)** (swept 0.10, 0.15, 0.20) | Ground-truth oracle label: assigns `label = "good"` if $q_{\text{true}} \ge \text{hurdle}$, `"bad"` if $q_{\text{true}} < \text{hurdle}$. Exists only for post-hoc scoring. |
| **Benchmark Runner Hardcoded Hurdle** | [`backend/benchmark/runner.py:207-208`](file:///d:/Developer/qualloop/backend/benchmark/runner.py#L207-L208) `is_good_ad` / `is_poor_ad` | **Hardcoded** | **`0.15` / `0.05`** | Non-preset ads classified as: `is_good = (gt_intent >= 0.15)`, `is_poor = (gt_intent < 0.05)`. Creates an unlabeled dead zone between 0.05 and 0.15. |
| **Synthetic Scenarios Hurdle** | [`scratch/run_policy_ablation_v1.py:37`](file:///d:/Developer/qualloop/scratch/run_policy_ablation_v1.py#L37) `HURDLE` | **Hardcoded** | **`0.15` (15%)** | Used to generate labels for continuous intent scenarios in Step 4B/4C/4D benchmarks. |
| **Production High CPQL Threshold** | [`backend/decision_engine/engine.py:37`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L37) `high_cpql_lower_bound` | Yes (`DecisionPolicy`) | **`500.0`** | Evaluated in Rule 8: Triggers generic reallocation warning when $\text{CPQL}_{\text{low}} > 500.0$. *(Note: Step 4D benchmark mistakenly set this to 75.0).* |
| **Production Target CPQL** | [`backend/decision_engine/engine.py:38`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L38) `target_cpql` | Yes (`DecisionPolicy`) | **`75.0`** | Evaluated in Rule 9: Recommends budget increase when $\text{CPQL}_{\text{high}} < 75.0$. |
| **Production Spend Cap Guardrail** | [`backend/decision_engine/engine.py:44`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L44) `guardrail_action_spend_cap` | Yes (`DecisionPolicy`) | **`500.0`** | Controls action tier: spend $\le 500 \implies$ `PAUSE_AD` (auto-applied); spend $> 500 \implies$ `CONSIDER_PAUSE` (human review). |
| **Production Minimum Spend Guardrail** | [`backend/decision_engine/engine.py:41`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L41) `budget_guardrail_min_spend` | Yes (`DecisionPolicy`) | **`100.0`** | Suppresses pause actions if cumulative ad spend is below ₹100.00. |

### Metric Definition Semantics
- **False Pause:** An ad whose ground truth is good ($q_{\text{true}} \ge \tau_{\text{biz}}$) that receives `PAUSE_AD` or `CONSIDER_PAUSE` at any sequential checkpoint ($D \in \{3, 7, 14, 21\}$).
  $$\text{FPR} = \frac{\text{False Pauses}}{N_{\text{good}}}$$
- **Missed Poor Ad:** An ad whose ground truth is poor ($q_{\text{true}} < \tau_{\text{biz}}$) that runs through Day 28 without ever being paused.
  $$\text{MPR} = \frac{\text{Missed Poor Ads}}{N_{\text{poor}}}$$
- **Causal Source of Metric Differences:**
  When evaluating an identical frozen policy execution under two different scoring hurdles ($\tau_{\text{biz}} = 0.10$ vs $\tau_{\text{biz}} = 0.15$), any ad with $q_{\text{true}} \in [0.10, 0.15)$ is classified as **Good** under the 10% hurdle and **Poor** under the 15% hurdle. This shifts ads between denominators ($N_{\text{good}}$ vs $N_{\text{poor}}$) without changing any runtime policy action.

---

## 2. Aligned Results Across Dual Scoring Thresholds

Evaluated deterministically across the frozen 190 paired simulation runs (450 total ads; 50 continuous, 50 bimodal, 90 presets).  
For each policy, sequential checkpoints, ad spend, and lead generation were **100% frozen and identical** across both scoring views.

### 2.1 Complete Comparative Matrix

| Policy | Policy Decision Threshold | Scoring Hurdle ($\tau_{\text{biz}}$) | Good Ads ($N_{\text{good}}$) | Poor Ads ($N_{\text{poor}}$) | False Pauses (Rate [95% Wilson CI]) | Missed Poor Ads (Rate [95% Wilson CI]) | Spend on Poor Ads (Paused / Missed) | Total Spend | Total QL (M1 / M2) | Lost QL on Good Ads (M1 / M2) | Portfolio CPQL (M1 / M2) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **PROD_P10**<br>*(ci=0.90, N=20)* | **0.10** | **0.10 (10%)** | 290 | 160 | **3** (1.03% [0.35%, 3.00%]) | **97** (60.62% [52.89%, 67.86%]) | ₹653,000<br>(₹222k / ₹431k) | ₹2,158,000 | 5,226 / 5,190 | 9 / 13 | ₹412.94 / ₹415.80 |
| **PROD_P10**<br>*(ci=0.90, N=20)* | **0.10** | **0.15 (15%)** | 262 | 188 | **1** (0.38% [0.07%, 2.13%]) | **123** (65.43% [58.38%, 71.85%]) | ₹790,500<br>(₹229.5k / ₹561k) | ₹2,158,000 | 5,226 / 5,190 | 7 / 8 | ₹412.94 / ₹415.80 |
| **PROD_P15**<br>*(ci=0.90, N=20)* | **0.15** | **0.10 (10%)** | 290 | 160 | **9** (3.10% [1.64%, 5.79%]) | **50** (31.25% [24.58%, 38.80%]) | ₹571,500<br>(₹370.5k / ₹201k) | ₹2,067,750 | 5,171 / 5,107 | 22 / 32 | ₹399.87 / ₹404.89 |
| **PROD_P15**<br>*(ci=0.90, N=20)* | **0.15** | **0.15 (15%)** | 262 | 188 | **4** (1.53% [0.60%, 3.86%]) | **73** (38.83% [32.15%, 45.95%]) | ₹705,250<br>(₹389.2k / ₹316k) | ₹2,067,750 | 5,171 / 5,107 | 17 / 24 | ₹399.87 / ₹404.89 |
| **CONFIG_A_P15**<br>*(ci=0.80, N=12)* | **0.15** | **0.10 (10%)** | 290 | 160 | **24** (8.28% [5.62%, 12.02%]) | **28** (17.50% [12.39%, 24.13%]) | ₹469,500<br>(₹374.5k / ₹95k) | ₹1,927,250 | 5,012 / 4,885 | 106 / 148 | ₹384.53 / ₹394.52 |
| **CONFIG_A_P15**<br>*(ci=0.80, N=12)* | **0.15** | **0.15 (15%)** | 262 | 188 | **15** (5.73% [3.50%, 9.23%]) | **47** (25.00% [19.35%, 31.65%]) | ₹590,750<br>(₹400.7k / ₹190k) | ₹1,927,250 | 5,012 / 4,885 | 73 / 106 | ₹384.53 / ₹394.52 |

*M1: Pipeline-harvest qualified leads (leads created before pause). M2: Strictly resolved at or before pause.*

### 2.2 Causal Decomposition of Result Differences
1. **For PROD_P10 across scoring views:**
   - **Policy Action Difference:** **0** (identical pause decisions, identical checkpoints).
   - **Label & Denominator Shift:** Exactly 28 ads have $q_{\text{true}} \in [0.10, 0.15)$. Under 10% hurdle, they are labeled Good ($N_{\text{good}}=290$); under 15% hurdle, they are labeled Poor ($N_{\text{poor}}=188$).
   - **Impact on Metrics:** Because PROD_P10 is designed not to pause ads with $q \ge 0.10$, 26 of these 28 ads ran to Day 28 unpaused. Under the 15% hurdle scoring, they are penalized as "missed poor ads", driving missed poor ads up from 97 to 123 (60.6% $\to$ 65.4%) and spend on poor ads from ₹653k to ₹790.5k. This difference is **100% artifactual label shift, with zero change in policy behavior**.
2. **Comparing PROD_P10 vs PROD_P15 (Action Difference):**
   - Under the 15% scoring hurdle: PROD_P15 pauses 53 additional ads (119 vs 66 pauses).
   - It eliminates 50 poor ads (missed poor drops from 123 to 73), saving ₹85,250 in spend on poor ads.
   - However, it causes 3 additional false pauses on good ads, losing 10 qualified leads (lost leads rise from 7 to 17).

---

## 3. Discovered & Corrected Metric-Definition Defects

1. **Defect 1: Denominator Conflation & Undefined Middle Intent**
   - *Previous Defect:* `backend/benchmark/runner.py:207-208` defined good as $\ge 0.15$ and poor as $< 0.05$, silently dropping ads with intent between $0.05$ and $0.15$ from both denominators.
   - *Correction:* The aligned runner partitions the entire space into mutually exclusive and exhaustive sets: $q \ge \tau_{\text{biz}} \iff \text{Good}$, $q < \tau_{\text{biz}} \iff \text{Poor}$. Denominators sum exactly to 450 in all runs ($290 + 160 = 450$ at 0.10; $262 + 188 = 450$ at 0.15).

2. **Defect 2: Lead Accounting Leakage (M1 vs M2)**
   - *Previous Defect:* In Step 4D, some analysis scripts evaluated qualified leads using full-horizon outcomes as if paused campaigns were allowed to collect conversions indefinitely.
   - *Correction:* Separated into:
     - **Metric 1 (Pipeline Harvest):** Includes only leads generated before the pause timestamp that qualify post-pause.
     - **Metric 2 (Strict Decision-Time Resolution):** Includes only leads whose qualification was already fully resolved at the exact checkpoint.
     - No future leads created after pause day are ever credited.

3. **Defect 3: Conflation of Policy Threshold with Business Standard**
   - *Previous Defect:* Benchmark scripts coupled the policy's decision threshold with the evaluation hurdle, making it impossible to evaluate how the production policy behaves against higher or lower business standards.
   - *Correction:* Decoupled the policy's configured `low_qualification_upper_bound` from the post-hoc scoring hurdle $\tau_{\text{biz}}$, enabling objective counterfactual assessment.

---

## 4. Economic Regret Formulation & Sensitivity Analysis

### 4.1 Missing Business Inputs
The simulator does **not** model:
- Contribution margin / revenue per qualified lead ($V_{\text{QL}}$).
- Contractual or operational penalties for pausing active campaigns.
- Downstream sales closing rates.

**We do not invent arbitrary values.** Instead, we define a parameterized economic regret model.

### 4.2 Formal Regret Definition
Relative to an Oracle that never pauses good ads and pauses poor ads at the earliest data-mature checkpoint ($t_{\text{min}} = \text{Day } 14$):
$$\text{Regret}(\pi; V_{\text{QL}}) = A(\pi) + B(\pi) \cdot V_{\text{QL}}$$
where:
$$A(\pi) = \sum_{\text{poor ads } j} [S_j(\pi) - S_j(\text{Oracle})] - \sum_{\text{good ads } i} [S_i(\text{Oracle}) - S_i(\pi)] \quad (\text{Net Spend Waste})$$
$$B(\pi) = \sum_{\text{good ads } i} [QL_i(\text{Oracle}) - QL_i(\pi)] - \sum_{\text{poor ads } j} [QL_j(\pi) - QL_j(\text{Oracle})] \quad (\text{Net Lost Qualified Leads})$$

### 4.3 Policy Regret Parameters (Under 15% Business Hurdle)

$$\text{Regret}_{\text{PROD\_P10}}(V_{\text{QL}}) = ₹333,000.00 - (278 \times V_{\text{QL}})$$
$$\text{Regret}_{\text{PROD\_P15}}(V_{\text{QL}}) = ₹242,750.00 - (223 \times V_{\text{QL}})$$
$$\text{Regret}_{\text{CONFIG\_A\_P15}}(V_{\text{QL}}) = ₹102,250.00 - (64 \times V_{\text{QL}})$$

### 4.4 Sensitivity Grid & Crossover Analysis

| Lead Value ($V_{\text{QL}}$) | Regret PROD_P10 (Thresh 0.10) | Regret PROD_P15 (Thresh 0.15) | Regret CONFIG_A_P15 (Config A) | Optimal Policy under this Economic Assumption |
|---|---|---|---|---|
| **₹100 / lead** | ₹305,200 | ₹220,450 | **₹95,850** | **Config A** (Aggressive pruning minimizes spend waste) |
| **₹300 / lead** | ₹249,600 | ₹175,850 | **₹83,050** | **Config A** (Spend savings still exceed value of lost leads) |
| **₹500 / lead** | ₹194,000 | ₹131,250 | **₹70,250** | **Config A** (Config A remains superior at low margins) |
| **₹1,000 / lead** | ₹55,000 | **₹19,750** | ₹38,250 | **PROD_P15** (Balanced trade-off between bad spend & lost leads) |
| **₹1,078.27 / lead** | ₹33,239 | **₹2,296** | **₹33,239** | **Crossover:** PROD_P10 ties Config A |
| **₹1,500 / lead** | −₹84,000 | **−₹91,750** | +₹6,250 | **PROD_P15** (Revenue preservation strongly penalizes Config A) |
| **₹1,640.91 / lead** | **−₹123,173** | **−₹123,173** | +₹17,232 | **Crossover:** PROD_P10 ties PROD_P15 |
| **₹2,000 / lead** | **−₹223,000** | −₹203,250 | −₹25,750 | **PROD_P10** (Zero-false-pause policy wins; lead loss is fatal) |

#### Takeaway:
- If a qualified lead is worth **less than ₹1,078**, aggressive pruning (Config A) minimizes economic regret because saving media spend matters more than preserving marginal leads.
- If a qualified lead is worth **between ₹1,078 and ₹1,641**, the balanced policy (**PROD_P15**) minimizes regret.
- If a qualified lead is worth **more than ₹1,641**, the ultra-conservative production baseline (**PROD_P10**) minimizes regret because even a tiny false-pause rate destroys immense economic value.

---

## 5. Verification Evidence & Test Results

1. **Automated Semantics & Regret Suite ([`backend/tests/test_step_4d5_semantics.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d5_semantics.py)):**
   - `test_policy_threshold_independent_of_scoring_hurdle`: Verified threshold separation.
   - `test_scoring_hurdle_label_reclassification_and_denominators`: Verified denominator partition.
   - `test_metric1_pipeline_vs_metric2_resolved_accounting`: Verified pipeline harvest vs decision-time resolution.
   - `test_economic_regret_linear_form_and_crossover`: Verified monotonicity and analytical crossover solver.
   - **Result:** 4 passed in 4.20s.
2. **Full Backend Test Suite:**
   - Command: `pytest backend/tests`
   - **Result: 179 passed, 1 warning in 52.61s.**
3. **Repository Integrity:**
   - Working tree clean; zero production code or defaults modified; zero commits.

---

## 6. Recommendations for the Next Experiment

1. **Do NOT Tune Production Defaults Without a Business $V_{\text{QL}}$ Anchor:**
   - The debate between Config A (aggressive), PROD_P15 (moderate), and PROD_P10 (conservative) cannot be resolved by statistical metrics alone.
   - As proven by the crossover analysis, the "best" policy flips entirely depending on whether a qualified lead is worth ₹500 or ₹2,000.
2. **Secure the Commercial Stakeholder Value:**
   - Obtain from business stakeholders the estimated customer lifetime value (LTV) and sales qualification conversion value ($V_{\text{QL}}$).
3. **Next Technical Step:**
   - Once $V_{\text{QL}}$ is specified, run an economic optimization grid over `(ci_level, min_mature_contacts, threshold)` targeting minimum expected economic regret rather than arbitrary false-pause percentages.
   - Retain frozen paired simulations as the canonical offline validation harness.
