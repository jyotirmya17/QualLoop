# QualLoop Benchmark Reconciliation & Performance Report

**Generated At:** 2026-10-29T02:59:52.434352+00:00  
**Dataset Partition:** Holdout (100 seeds, 9 scenarios)  
**Total Advertisements:** 175 (140 Good, 35 Poor)  
**Frozen Policy:** Config 2 (Frozen) (argmin(FNDR) subject to bounded sequential FPPR on 100 tuning seeds)  

---

## 1. Per-Scenario Reconciled Count & False-Pause Breakdown

All counts below directly sum to the exact aggregate values (100 Seeds / 175 Ads / 140 Good / 35 Poor). False Positive Pause Rate (FPPR) is defined strictly over **Good Ads** ($N_{\text{good}} = 140$).

| Scenario | Seeds | Budget (₹) | Total Ads | Good Ads | Poor Ads | QualLoop FP | Baseline B FP | Baseline A FP | Baseline C FP |
|---|---|---|---|---|---|---|---|---|---|
| `bad_ad_high_engagement` | 13 | ₹130,000 | 26 | 13 | 13 | 0 (0.0%) | 10 (76.9%) | 0 (0.0%) | 0 (0.0%) |
| `creative_fatigue` | 10 | ₹70,000 | 10 | 10 | 0 | 0 (0.0%) | 9 (90.0%) | 0 (0.0%) | 1 (10.0%) |
| `delayed_conversion_trap` | 13 | ₹65,000 | 13 | 13 | 0 | 1 (7.7%) | 10 (76.9%) | 0 (0.0%) | 2 (15.4%) |
| `good_ad_low_reachability` | 12 | ₹120,000 | 24 | 24 | 0 | 0 (0.0%) | 18 (75.0%) | 0 (0.0%) | 5 (20.8%) |
| `healthy_campaign` | 15 | ₹150,000 | 45 | 45 | 0 | 0 (0.0%) | 31 (68.9%) | 0 (0.0%) | 4 (8.9%) |
| `high_cpql` | 7 | ₹140,000 | 7 | 7 | 0 | 0 (0.0%) | 7 (100.0%) | 7 (100.0%) | 1 (14.3%) |
| `mixed_portfolio` | 10 | ₹100,000 | 30 | 20 | 10 | 1 (5.0%) | 15 (75.0%) | 0 (0.0%) | 6 (30.0%) |
| `small_sample_trap` | 12 | ₹6,000 | 12 | 0 | 12 | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| `sudden_deterioration` | 8 | ₹40,000 | 8 | 8 | 0 | 0 (0.0%) | 5 (62.5%) | 0 (0.0%) | 0 (0.0%) |
| **TOTAL** | **100** | **₹821,000** | **175** | **140** | **35** | **2 (1.4%)** | **105 (75.0%)** | **7 (5.0%)** | **19 (13.6%)** |

### Count Reconciliations Explained
- **`healthy_campaign` seed count:** Exactly 15 holdout seeds (seeds 1016 to 1030). Each seed simulates 3 ads with spend ₹5,000 + ₹4,500 + ₹500 = ₹10,000, perfectly accounting for the ₹150,000 budget and 45 ads. (The 30-seed count in earlier docs refers to the combined 200-seed dataset: 15 tuning + 15 holdout).
- **Baseline B false pauses (105 / 140):** An observer looking at scenario false-pause rates (e.g. 76.9% in `bad_ad_high_engagement` and 75.0% in `mixed_portfolio`) might mistakenly multiply by the scenario's *Total Ads* (26 and 30), calculating ~123 false pauses. However, FPPR is defined strictly over **Good Ads** (13 and 20). Evaluated against the 140 good ads, Baseline B's per-scenario false pauses are `[31, 18, 10, 0, 10, 9, 15, 7, 5]`, which sum **exactly to 105** (75.00%).

---

## 2. Fixed Redistributed Budget Headline Performance (Both Return Models)

Under fixed total budget (₹821,000 holdout budget), budget freed by paused ads is redistributed equally among surviving active ads in the same campaign. Any budget remaining when all ads in an ad set/campaign are paused is recorded as **unspent budget (wasted)**. The headline metric is **Total Qualified Leads at fixed budget**, with unspent budget counted as wasted. Headline CPQL is $\text{Budget} / \text{Qualified Leads}$.

> [!NOTE]
> **QL-per-rupee columns are excluded:** In variable budget mode, Baseline B prematurely paused 75.0% of good ads early, slashing spend while capturing initial leads, which yielded an artificially inflated QL/rupee ratio (0.004543) that exceeds the omniscient Oracle (0.003881) despite sacrificing over 61% of total qualified volume. Comparing QL/rupee when an inferior policy exceeds the Oracle is deceptive. Total qualified leads at fixed budget is the true headline metric.

### A. Linear Returns Model (Leads Proportional to Spend, $Spend^{1.0}$)

| Policy | Budget (₹) | Realized Spend | Unspent Budget | Total Qualified Leads | Headline CPQL (₹) | False Pauses (FPPR) | Missed Bad Ads (FNDR) |
|---|---|---|---|---|---|---|---|
| **Oracle (Day-0 Ground Truth)** | ₹821,000 | ₹814,999.40 | ₹6,000.60 | **5,518.55** | **₹148.77** | 0/140 (0.0%) | 0/35 (0.0%) |
| **QualLoop (Uncertainty-Aware)** | ₹821,000 | ₹818,499.17 | ₹2,500.83 | **4,805.88** | **₹170.83** | 2/140 (1.4%) | 13/35 (37.1%) |
| **Baseline C (Maturity-Aware Naive)** | ₹821,000 | ₹808,449.28 | ₹12,550.72 | **4,737.22** | **₹173.31** | 19/140 (13.6%) | 10/35 (28.6%) |
| **Baseline A (Top-of-Funnel CPL)** | ₹821,000 | ₹698,856.16 | ₹122,143.84 | **4,372.24** | **₹187.78** | 7/140 (5.0%) | 35/35 (100.0%) |
| **Baseline B (Heuristic Failure)** | ₹821,000 | ₹338,720.87 | ₹482,279.13 | **2,515.12** | **₹326.43** | 105/140 (75.0%) | 0/35 (0.0%) |

### B. Diminishing Returns Model (Leads Proportional to $Spend^{0.7}$)

| Policy | Budget (₹) | Realized Spend | Unspent Budget | Total Qualified Leads | Headline CPQL (₹) | False Pauses (FPPR) | Missed Bad Ads (FNDR) |
|---|---|---|---|---|---|---|---|
| **Oracle (Day-0 Ground Truth)** | ₹821,000 | ₹814,999.40 | ₹6,000.60 | **4,079.79** | **₹201.24** | 0/140 (0.0%) | 0/35 (0.0%) |
| **QualLoop (Uncertainty-Aware)** | ₹821,000 | ₹818,499.17 | ₹2,500.83 | **3,739.50** | **₹219.55** | 2/140 (1.4%) | 13/35 (37.1%) |
| **Baseline C (Maturity-Aware Naive)** | ₹821,000 | ₹808,449.28 | ₹12,550.72 | **3,675.48** | **₹223.37** | 19/140 (13.6%) | 10/35 (28.6%) |
| **Baseline A (Top-of-Funnel CPL)** | ₹821,000 | ₹698,856.16 | ₹122,143.84 | **3,516.12** | **₹233.50** | 7/140 (5.0%) | 35/35 (100.0%) |
| **Baseline B (Heuristic Failure)** | ₹821,000 | ₹338,720.87 | ₹482,279.13 | **1,751.77** | **₹468.67** | 105/140 (75.0%) | 0/35 (0.0%) |

---

## 3. Variable Budget Performance (Stopping Spend on Paused Ads)

| Policy | Budget (₹) | Realized Spend | Unspent Budget | Total Qualified Leads | Realized CPQL (₹) | False Pauses (FPPR) | Missed Bad Ads (FNDR) |
|---|---|---|---|---|---|---|---|
| **Oracle** | ₹821,000 | ₹681,000.00 | ₹140,000.00 | 2,643.00 | ₹257.66 | 0/140 (0.0%) | 0/35 (0.0%) |
| **QualLoop** | ₹821,000 | ₹757,750.00 | ₹63,250.00 | 2,690.00 | ₹281.69 | 2/140 (1.4%) | 13/35 (37.1%) |
| **Baseline C** | ₹821,000 | ₹723,700.00 | ₹97,300.00 | 2,604.00 | ₹277.92 | 19/140 (13.6%) | 10/35 (28.6%) |
| **Baseline A** | ₹821,000 | ₹698,857.16 | ₹122,142.84 | 2,684.00 | ₹260.38 | 7/140 (5.0%) | 35/35 (100.0%) |
| **Baseline B** | ₹821,000 | ₹221,453.46 | ₹599,546.54 | 1,006.00 | ₹220.13 | 105/140 (75.0%) | 0/35 (0.0%) |

---

## 4. Economic vs. Intent Labeling: The `high_cpql` Paradox

Each advertisement is evaluated under two independent ground-truth standards:
1. **Intent Ground Truth ($q \ge 15.0\%$):** Pure conversion probability among contacted leads ($N_{\text{good}} = 140, N_{\text{poor}} = 35$).
2. **Economic Ground Truth (True $\text{CPQL} \le ₹600.00$):** Unit economic viability against campaign target CPQL ($N_{\text{good}} = 133, N_{\text{poor}} = 42$).

> [!IMPORTANT]
> **Key Insight:** `high_cpql` is **good by intent** ($q = 20.0\% \ge 15.0\%$) but **poor by economics** (realized CPQL $\approx ₹2,976.19 \gg ₹600.00$ target ceiling). Under intent labeling, Baseline A's early Day-3 pause of all 7 `high_cpql` ads is penalized as a false pause (FPPR = 5.00%). Under economic labeling, cutting ₹122,143 of wasteful spend is economically optimal, dropping Baseline A's false pause rate to **0.00% (0/133)**. QualLoop lets `high_cpql` run to completion, spending ₹140,000 to deliver only 47 qualified leads.

| Policy | FPPR by Intent (q ≥ 15%) | FPPR by Economics (CPQL ≤ ₹600) | FNDR by Intent (Missed Bad) | FNDR by Economics (Missed Bad) |
|---|---|---|---|---|
| **Oracle** | 0/140 (0.0%) | 0/133 (0.0%) | 0/35 (0.0%) | 7/42 (16.7%) |
| **QualLoop** | 2/140 (1.4%) | 2/133 (1.5%) | 13/35 (37.1%) | 20/42 (47.6%) |
| **Baseline C** | 19/140 (13.6%) | 18/133 (13.5%) | 10/35 (28.6%) | 16/42 (38.1%) |
| **Baseline A** | 7/140 (5.0%) | 0/133 (0.0%) | 35/35 (100.0%) | 35/42 (83.3%) |
| **Baseline B** | 105/140 (75.0%) | 98/133 (73.7%) | 0/35 (0.0%) | 0/42 (0.0%) |

---

## 5. Auto-Generated Losses Against Baselines (20 in Fixed Budget)

| Scenario | Opponent Baseline | Metric | QualLoop Value | Baseline Value | Reason |
|---|---|---|---|---|---|
| `bad_ad_high_engagement` | `baseline_b` | `ql_per_rupee` | 0.010519 | 0.013362 | QualLoop had lower QL/rupee than baseline_b (0.010519 vs 0.013362) |
| `bad_ad_high_engagement` | `baseline_b` | `days_to_pause` | 15.08 | 3.0 | QualLoop took longer to pause bad ads than baseline_b (15.08d vs 3.0d) |
| `bad_ad_high_engagement` | `baseline_c` | `qualified_leads` | 1367.5 | 1429.38 | QualLoop yielded fewer qualified leads than baseline_c (1367.5 vs 1429.38) |
| `bad_ad_high_engagement` | `baseline_c` | `ql_per_rupee` | 0.010519 | 0.010995 | QualLoop had lower QL/rupee than baseline_c (0.010519 vs 0.010995) |
| `bad_ad_high_engagement` | `baseline_c` | `cpql` | 95.06 | 90.95 | QualLoop had higher CPQL than baseline_c (Rs 95.06 vs Rs 90.95) |
| `bad_ad_high_engagement` | `baseline_c` | `days_to_pause` | 15.08 | 14.0 | QualLoop took longer to pause bad ads than baseline_c (15.08d vs 14.0d) |
| `delayed_conversion_trap` | `baseline_a` | `qualified_leads` | 242.0 | 252.0 | QualLoop yielded fewer qualified leads than baseline_a (242.0 vs 252.0) |
| `delayed_conversion_trap` | `baseline_a` | `ql_per_rupee` | 0.003872 | 0.003877 | QualLoop had lower QL/rupee than baseline_a (0.003872 vs 0.003877) |
| `delayed_conversion_trap` | `baseline_a` | `cpql` | 268.6 | 257.94 | QualLoop had higher CPQL than baseline_a (Rs 268.6 vs Rs 257.94) |
| `delayed_conversion_trap` | `baseline_a` | `false_pause_rate` | 0.0769 | 0.0 | QualLoop had higher false pause rate than baseline_a (7.69% vs 0.00%) |
| `mixed_portfolio` | `baseline_b` | `missed_bad_ad_rate` | 0.1 | 0.0 | QualLoop missed more bad ads than baseline_b (10.00% vs 0.00%) |
| `mixed_portfolio` | `baseline_b` | `days_to_pause` | 16.33 | 4.1 | QualLoop took longer to pause bad ads than baseline_b (16.33d vs 4.1d) |
| `mixed_portfolio` | `baseline_a` | `false_pause_rate` | 0.05 | 0.0 | QualLoop had higher false pause rate than baseline_a (5.00% vs 0.00%) |
| `mixed_portfolio` | `baseline_c` | `qualified_leads` | 450.42 | 501.39 | QualLoop yielded fewer qualified leads than baseline_c (450.42 vs 501.39) |
| `mixed_portfolio` | `baseline_c` | `ql_per_rupee` | 0.004504 | 0.005014 | QualLoop had lower QL/rupee than baseline_c (0.004504 vs 0.005014) |
| `mixed_portfolio` | `baseline_c` | `cpql` | 222.02 | 199.45 | QualLoop had higher CPQL than baseline_c (Rs 222.02 vs Rs 199.45) |
| `mixed_portfolio` | `baseline_c` | `missed_bad_ad_rate` | 0.1 | 0.0 | QualLoop missed more bad ads than baseline_c (10.00% vs 0.00%) |
| `mixed_portfolio` | `baseline_c` | `days_to_pause` | 16.33 | 14.7 | QualLoop took longer to pause bad ads than baseline_c (16.33d vs 14.7d) |
| `small_sample_trap` | `baseline_b` | `missed_bad_ad_rate` | 1.0 | 0.0 | QualLoop missed more bad ads than baseline_b (100.00% vs 0.00%) |
| `small_sample_trap` | `baseline_c` | `missed_bad_ad_rate` | 1.0 | 0.8333 | QualLoop missed more bad ads than baseline_c (100.00% vs 83.33%) |

---

## 6. Tuned Baseline C Comparison (Pre-Stated Rule on 100 Holdout Seeds)

Baseline C was tuned on the 100 tuning seeds across a 12-configuration grid (min mature contacts $\in \{10, 15, 20, 30\} \times \text{hurdle} \in \{0.10, 0.12, 0.15\}$) using the identical pre-stated selection rule as QualLoop: $\arg\min(\text{FNDR}) \text{ s.t. } \text{FPPR} \le 4.00\%$.

- **Winning Frozen Config:** Min Mature Contacts = 30, Qualification Hurdle = 0.10 (Tuning FPPR = 3.57%, FNDR = 37.14%).
- **Holdout Fixed-Budget Total Leads:** QualLoop = **4,805.88** vs. Tuned Baseline C = **4,840.88**.
- **Paired Difference (QualLoop minus Tuned C):** $\Delta = -0.35$ leads/run ($p = 0.5116$; Wilcoxon $p = 0.5898$).
- **Scenario-Stratified Bootstrap 95% CI:** `[-1.44, 0.57]` (spans zero).
- **Honest Verdict:** When Baseline C is properly tuned, **QualLoop and Tuned Baseline C are statistically indistinguishable on total qualified leads at fixed budget**.

---

## 7. Comprehensive Limitations & Empirical Boundary Realities

1. **Synthetic Data Prototype:** QualLoop operates exclusively on simulated data with idealized Beta-Binomial generation. It has not been validated against live Meta/Google ad auction dynamics.
2. **Boundary Instability on Continuous Intent:** While false pause rates are 1.4% on discrete bimodal clusters (4% vs 25%), they jump to **23.5% (8/34)** when buying intent is drawn from a continuous distribution ($0.03 + \text{Beta}(2, 6) \times 0.32$). Fixed thresholds suffer severe classification noise near the hurdle.
3. **Statistical Parity with Tuned Naive Heuristics:** QualLoop does not produce superior lead volume compared to an optimally tuned point heuristic (Tuned Baseline C delivers 4,840.88 leads vs QualLoop's 4,805.88; 95% bootstrap CI `[-1.44, 0.57]`). QualLoop's true value lies in principled credible intervals, auditability, and safety guarantees—not gross lead maximization.
4. **Diminishing Returns Sensitivity:** Under linear spend scaling ($Spend^{1.0}$), QualLoop produces 4,805.88 leads; under diminishing returns ($Spend^{0.7}$), reallocated spend suffers saturation fatigue, reducing lead yield to 3,739.50 (-22.2%).
5. **Static Maturity Constants:** Contact maturity (3 days) and qualification maturity (7 days) are uniform constants. In real sales pipelines, lead contactability exhibits heavy-tailed Pareto delay dynamics.
6. **Intent vs. Economic Divergence:** `high_cpql` proves that high qualification intent ($q=20\%$) can still be commercially catastrophic if top-of-funnel CPL is uncalibrated ($CPQL \approx ₹2,976 \gg ₹500$). Focusing exclusively on qualification conversion without CPQL gating leaves advertising budgets vulnerable.
7. **Dry-Run Meta CAPI Interface:** The feedback module formats and SHA-256 hashes CAPI events according to Meta Graph API specifications, but transmits zero live network traffic to Meta servers.
