# QualLoop Step 4D.3 — Controlled Policy Ablation Report

**Auditor:** Skeptical ML Evaluation Engineer  
**Date:** 2026-10-27  
**Artifacts Generated:**  
- `scratch/step_4d3_reconciliation.md`  
- `scratch/run_policy_ablation_v1.py`  
- `scratch/policy_ablation_results_v1.json`  

---

## 1. Executive Summary & Headline Findings

This study performed a rigorous, controlled 2x2 factorial ablation to isolate the causal effects of the minimum mature contact threshold ($N_{min}$) across the Estimator and the Decision Policy.

### Factorial Matrix Evaluated
1. **Config A (Baseline):** Estimator $N_{min} = 12$, Policy $N_{min} = 12$
2. **Config B (Estimator-only):** Estimator $N_{min} = 20$, Policy $N_{min} = 12$
3. **Config C (Policy-only):** Estimator $N_{min} = 12$, Policy $N_{min} = 20$
4. **Config D (Both):** Estimator $N_{min} = 20$, Policy $N_{min} = 20$

### Key Empirical Findings
1. **Equivalence of B, C, and D in Decision Execution:**
   Configs B, C, and D produce **identical pause actions, identical spend, identical lead yields, and identical CPQL** across all 190 simulation runs (450 ads). They differ solely in whether non-pauses between 12 and 19 contacts are labeled `COLLECT_MORE_DATA` (Rule 3 in C and D: 1,236 events) versus `CONTINUE_MONITORING` (Rule 10 in B: 976 events).
2. **Higher Contact Threshold ($N_{min} = 20$) Degrades Portfolio Efficiency:**
   - **False Pauses:** Marginally drops from 12 to 10 ($-0.91\%$, $p = 0.41$, **not statistically significant**).
   - **Missed Poor Ads:** Increases significantly from 60 (25.97%) to 77 (33.33%) ($+7.36\%$, paired t $p = 0.0014$).
   - **Poor Ad Pause Latency:** The median pause day shifts from **Day 14** (Config A) to **Day 21** (Configs B/C/D).
   - **Wasted Poor Spend:** Accrues $+₹123,250.00$ in unnecessary spend on poor ads ($+₹648.68$/run, $p = 1.76 \times 10^{-13}$).
   - **Macro CPQL:** Worsens by **$+₹18.03$/lead** (from ₹397.53 in A to ₹415.56 in B/C/D).
3. **Recommendation:**
   **Reject $N_{min} = 20$ and maintain the Baseline $N_{min} = 12$.** Bumping the threshold to 20 causes substantial economic harm by forcing bad ads to linger an extra 7 days without resolving false pauses on near-threshold good ads.

---

## 2. Experimental Setup & Precommitted Data Separation

To prevent data snooping and ensure unbiased validation:
- **Historical Splits Audited:**
  - Presets Tuning: Seeds 1001–1015, 2001–2013, 3001–3012, 4001–4013, 5001–5012, 6001–6010, 7001–7010, 8001–8008, 9001–9007
  - Presets Holdout: Seeds 1016–1030, 2014–2025, 3013–3025, 4014–4025, 5013–5025, 6011–6020, 7011–7020, 8009–8015, 9008–9015
  - Continuous Development Ablation (Step 4C): Seeds 7000–7049
  - Out-of-Sample Validation Split (Step 4D): Seeds 12000–12049, 14000–14049, 16001–16010
- **Precommitted Untouched Validation Split for Step 4D.3:**
  - **Continuous Intent:** 50 runs, seeds 22000–22049 (150 ads)
  - **Bimodal Synthetic:** 50 runs, seeds 24000–24049 (150 ads)
  - **Presets (9 Scenarios):** 10 runs each, seeds 26001–26010 (90 runs, 150 ads)
  - **Total:** 190 simulation runs (450 total ads per configuration).
  - *Integrity Guarantee:* None of these seeds were ever evaluated, inspected, or tuned on in any prior task.
- **Fixed Parameters Across All Four Configurations:**
  - Estimator Credible Interval Level: `ci_level = 0.80`
  - Maturity Fraction Threshold: `min_maturity_fraction = 0.50`
  - Low-Qualification Upper Bound: `low_qualification_upper_bound = 0.15`
  - High CPQL Lower Bound: `high_cpql_lower_bound = 75.0`
  - Decision Checkpoints: Days 3, 7, 14, 21 of a 28-day horizon

---

## 3. Comprehensive Macro Results Table (Untouched Validation Split)

*Never-Paused Reference Baseline (Counterfactual 28-day horizon with no pauses):*  
Total Spend: ₹2,275,000.00 | Total Qualified Leads: 5,007 | **Reference CPQL: ₹454.36**

| Metric | Config A (Baseline: Est 12, Pol 12) | Config B (Estimator-only: Est 20, Pol 12) | Config C (Policy-only: Est 12, Pol 20) | Config D (Both: Est 20, Pol 20) | Causal Effect of $N_{min}=20$ (D vs A) |
|---|---|---|---|---|---|
| **Runs Evaluated** | 190 | 190 | 190 | 190 | — |
| **Ads Evaluated** | 450 | 450 | 450 | 450 | — |
| **Good Ads (Ground Truth)** | 219 | 219 | 219 | 219 | — |
| **Poor Ads (Ground Truth)** | 231 | 231 | 231 | 231 | — |
| **False Pauses (Count)** | **12** | **10** | **10** | **10** | **−2** |
| **False Pause Rate** | **5.48% (12/219)** | **4.57% (10/219)** | **4.57% (10/219)** | **4.57% (10/219)** | **−0.91% ($p=0.41$)** |
| **Missed Poor Ads (Count)** | **60** | **77** | **77** | **77** | **+17** |
| **Missed Poor Ad Rate** | **25.97% (60/231)** | **33.33% (77/231)** | **33.33% (77/231)** | **33.33% (77/231)** | **+7.36% ($p=0.0014$)** |
| **Poor Ads Paused** | 171 | 154 | 154 | 154 | −17 |
| **Median Pause Day (Poor Ads)** | **Day 14.0** | **Day 21.0** | **Day 21.0** | **Day 21.0** | **+7.0 Days Latency** |
| • *Paused Day 14 (Poor)* | 130 | 46 | 46 | 46 | −84 |
| • *Paused Day 21 (Poor)* | 41 | 108 | 108 | 108 | +67 |
| • *False Pauses at Day 14* | 9 | 3 | 3 | 3 | −6 |
| • *False Pauses at Day 21* | 3 | 7 | 7 | 7 | +4 |
| **Poor Ad Spend (₹)** | **₹737,000.00** | **₹860,250.00** | **₹860,250.00** | **₹860,250.00** | **+₹123,250.00** |
| **Total Policy Spend (₹)** | **₹1,866,000.00** | **₹1,999,250.00** | **₹1,999,250.00** | **₹1,999,250.00** | **+₹133,250.00** |
| **Metric 1 Qualified Leads** | 4,694 | 4,811 | 4,811 | 4,811 | +117 |
| **Metric 2 Qualified Leads** | 4,551 | 4,707 | 4,707 | 4,707 | +156 |
| **Metric 1 CPQL (₹)** | **₹397.53** | **₹415.56** | **₹415.56** | **₹415.56** | **+₹18.03/lead (Worse)** |
| **Metric 2 CPQL (₹)** | **₹410.02** | **₹424.74** | **₹424.74** | **₹424.74** | **+₹14.72/lead (Worse)** |
| **Mean Per-Run CPQL (₹)** | ₹727.73 | ₹716.29 | ₹716.29 | ₹716.29 | −₹11.44 |
| **Zero-QL Runs Count** | 9 / 190 | 9 / 190 | 9 / 190 | 9 / 190 | 0 |
| **Insufficient Evidence Events** | 976 | 976 | **1,236** | **1,236** | +260 |

---

## 4. Breakdown by Scenario Family

### A. Continuous Intent (50 runs, 150 ads: 29 good, 121 poor)
- **Baseline A:** False Pauses: 11 / 29 (37.93%) | Missed Poor: 36 / 121 (29.75%) | Spend: ₹570,000.00 | M1 QL: 1,178 | CPQL: ₹483.87
- **Configs B, C, D:** False Pauses: 9 / 29 (31.03%) | Missed Poor: 41 / 121 (33.88%) | Spend: ₹628,750.00 | M1 QL: 1,223 | CPQL: ₹514.10
- *Finding:* In continuous intent, 9 false pauses remain even at $N_{min}=20$. Missed poor ads increase by 5, poor spend increases by ₹56,250, and CPQL worsens by **+₹30.23/lead**.

### B. Bimodal Synthetic (50 runs, 150 ads: 70 good, 80 poor)
- **Baseline A:** False Pauses: 0 / 70 (0.00%) | Missed Poor: 14 / 80 (17.50%) | Spend: ₹572,500.00 | M1 QL: 1,284 | CPQL: ₹445.87
- **Configs B, C, D:** False Pauses: 0 / 70 (0.00%) | Missed Poor: 24 / 80 (30.00%) | Spend: ₹642,500.00 | M1 QL: 1,351 | CPQL: ₹475.57
- *Finding:* In synthetic bimodal distributions (where poor ads have true intent $\le 0.06$), raising $N_{min}$ to 20 causes 10 additional poor ads to be missed entirely (+12.5% missed rate) and inflates CPQL by **+₹29.70/lead**.

### C. Standard Presets (90 runs, 150 ads: 120 good, 30 poor)
- **Baseline A:** False Pauses: 1 / 120 (0.83%) | Missed Poor: 10 / 30 (33.33%) | Spend: ₹723,500.00 | M1 QL: 2,232 | CPQL: ₹324.15
- **Configs B, C, D:** False Pauses: 1 / 120 (0.83%) | Missed Poor: 12 / 30 (40.00%) | Spend: ₹728,000.00 | M1 QL: 2,237 | CPQL: ₹325.44
- *Finding:* Preset benchmarks are virtually unaffected in false pauses (1 / 120 in all configs) with a minor CPQL penalty (+₹1.29/lead).

---

## 5. Paired Statistical Differences Relative to Baseline A (N = 190 Paired Runs)

The simulation run ($N=190$) is the independent statistical unit of analysis. Paired differences are computed as $X_{Candidate} - X_{Baseline}$ on the exact same simulation instance:

| Metric | Mean Paired Difference (D − A) | 95% Bootstrap CI | Paired t-test $p$-value | Wilcoxon Signed-Rank $p$-value | Statistical Conclusion |
|---|---|---|---|---|---|
| **False Pauses per Run** | **−0.0105** | [−0.0368, +0.0158] | $0.4157$ | $0.4142$ | **Not Significant** (CI includes zero) |
| **Missed Poor Ads per Run** | **+0.0895** | [+0.0368, +0.1474] | **$1.44 \times 10^{-3}$** | **$1.61 \times 10^{-3}$** | **Significant Increase in Missed Bad Ads** |
| **Poor Ad Spend per Run (₹)** | **+₹648.68** | [+₹497.37, +₹817.11] | **$1.76 \times 10^{-13}$** | **$2.93 \times 10^{-12}$** | **Highly Significant Spend Waste** |
| **Total Spend per Run (₹)** | **+₹701.32** | [+₹532.89, +₹881.61] | **$1.64 \times 10^{-13}$** | **$1.99 \times 10^{-12}$** | **Highly Significant Spend Inflation** |
| **Qualified Leads per Run** | **+0.6158** | [+0.4000, +0.8632] | **$5.32 \times 10^{-7}$** | **$2.27 \times 10^{-8}$** | Diminishing lead return (+₹1,139 per extra lead) |

---

## 6. Architectural Insights on Estimator vs Policy Thresholds

The 2x2 factorial design revealed why Config B (Estimator $N_{min}=20$, Policy $N_{min}=12$) behaves identically to Config C (Estimator $N_{min}=12$, Policy $N_{min}=20$):
1. **Rule Ordering Interaction:**
   In the Decision Engine, **Rule 6** (Low-Qualification Pause) explicitly requires:
   ```python
   if (estimate.qualification_ci_high < policy.low_qualification_upper_bound
       and estimate.evidence_sufficient_qualification):
       return CONSIDER_PAUSE
   ```
2. When $N_{mature} < 20$:
   - In **Config C**, Rule 3 fires directly: `estimate.n_mature_contacts < policy.min_mature_contacts_for_qualification` $\implies$ returns `COLLECT_MORE_DATA`.
   - In **Config B**, Rule 3 does not fire (since $N \ge 12$), but Rule 6 cannot trigger pause because `evidence_sufficient_qualification` is `False`. The ad falls through to Rule 10, returning `CONTINUE_MONITORING`.
   - In both cases, **the ad is not paused**. It continues spending until Day 21.
3. Therefore, raising either parameter to 20 acts as an effective hard brake on pausing poor ads at Day 14.

---

## 7. Final Recommendation

1. **Reject $N_{min} = 20$:** Do not adopt Config C or D. It costs QualLoop ₹123,250 in wasted spend, increases missed bad ads by +7.4%, and worsens CPQL by +₹18.03/lead.
2. **Retain Production Defaults:** Baseline Config A ($N_{min} = 12$) achieves superior CPQL (₹397.53 vs ₹415.56) and prunes bad ads 7 days faster.
3. **Address Continuous Intent False Pauses via Abstention, Not Contact Thresholds:** False pauses on continuous intent near the 0.15 hurdle ($q \in [0.154, 0.177]$) cannot be solved by bumping contact requirements. Future research should evaluate a narrow boundary abstention window ($\pm 1.5\%$ around the hurdle) or adaptive multi-checkpoint sequential tests rather than blanket sample size increases.
