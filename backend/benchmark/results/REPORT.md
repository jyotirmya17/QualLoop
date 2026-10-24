# QualLoop Benchmark Reconciliation & Performance Report

**Generated At:** 2026-10-24T13:40:32.090946+00:00  
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

## 2. Fixed Redistributed Budget Headline Performance

Under fixed total budget (₹825,000 holdout budget), budget freed by paused ads is redistributed equally among surviving active ads in the same campaign. Headline metrics are total Qualified Leads (QL) and Cost Per Qualified Lead (CPQL).

| Policy | Realized Spend | Qualified Leads | CPQL (₹) | False Pauses (FPPR) | Missed Bad Ads (FNDR) |
|---|---|---|---|---|---|
| **Oracle (Day-0 Ground Truth)** | ₹814,999.40 | **5,518.55** | **₹148.77** | 0/140 (0.0%) | 0/35 (0.0%) |
| **QualLoop (Uncertainty-Aware)** | ₹818,499.17 | **4,805.88** | **₹170.83** | 2/140 (1.4%) | 13/35 (37.1%) |
| **Baseline C (Maturity-Aware Naive)** | ₹808,449.28 | **4,737.22** | **₹173.31** | 19/140 (13.6%) | 10/35 (28.6%) |
| **Baseline A (Top-of-Funnel CPL)** | ₹698,856.16 | **4,372.24** | **₹187.78** | 7/140 (5.0%) | 35/35 (100.0%) |
| **Baseline B (Heuristic Failure)** | ₹338,720.87 | **2,515.12** | **₹326.43** | 105/140 (75.0%) | 0/35 (0.0%) |

---

## 3. Variable Budget Performance (Stopping Spend on Paused Ads)

| Policy | Cumulative Spend | Qualified Leads | Realized CPQL (₹) | False Pauses (FPPR) | Missed Bad Ads (FNDR) |
|---|---|---|---|---|---|
| **Oracle** | ₹681,000.00 | 2,643.00 | ₹257.66 | 0/140 (0.0%) | 0/35 (0.0%) |
| **QualLoop** | ₹757,750.00 | 2,690.00 | ₹281.69 | 2/140 (1.4%) | 13/35 (37.1%) |
| **Baseline C** | ₹723,700.00 | 2,604.00 | ₹277.92 | 19/140 (13.6%) | 10/35 (28.6%) |
| **Baseline A** | ₹698,857.16 | 2,684.00 | ₹260.38 | 7/140 (5.0%) | 35/35 (100.0%) |
| **Baseline B** | ₹221,453.46 | 1,006.00 | ₹220.13 | 105/140 (75.0%) | 0/35 (0.0%) |

---

## 4. Auto-Generated Losses Against Baselines (29 in Fixed Budget)

| Scenario | Opponent Baseline | Metric | QualLoop Value | Baseline Value | Reason |
|---|---|---|---|---|---|
| `bad_ad_high_engagement` | `baseline_b` | `ql_per_rupee` | 0.010519 | 0.013362 | QualLoop had lower QL/rupee than baseline_b (0.010519 vs 0.013362) |
| `bad_ad_high_engagement` | `baseline_b` | `days_to_pause` | 15.08 | 3.0 | QualLoop took longer to pause bad ads than baseline_b (15.08d vs 3.0d) |
| `bad_ad_high_engagement` | `baseline_c` | `qualified_leads` | 1367.5 | 1429.38 | QualLoop yielded fewer qualified leads than baseline_c (1367.5 vs 1429.38) |
| `bad_ad_high_engagement` | `baseline_c` | `ql_per_rupee` | 0.010519 | 0.010995 | QualLoop had lower QL/rupee than baseline_c (0.010519 vs 0.010995) |
| `bad_ad_high_engagement` | `baseline_c` | `cpql` | 95.06 | 90.95 | QualLoop had higher CPQL than baseline_c (Rs 95.06 vs Rs 90.95) |
| `bad_ad_high_engagement` | `baseline_c` | `days_to_pause` | 15.08 | 14.0 | QualLoop took longer to pause bad ads than baseline_c (15.08d vs 14.0d) |
| `creative_fatigue` | `baseline_b` | `ql_per_rupee` | 0.0028 | 0.003226 | QualLoop had lower QL/rupee than baseline_b (0.0028 vs 0.003226) |
| `creative_fatigue` | `baseline_c` | `ql_per_rupee` | 0.0028 | 0.002842 | QualLoop had lower QL/rupee than baseline_c (0.0028 vs 0.002842) |
| `delayed_conversion_trap` | `baseline_a` | `qualified_leads` | 242.0 | 252.0 | QualLoop yielded fewer qualified leads than baseline_a (242.0 vs 252.0) |
| `delayed_conversion_trap` | `baseline_a` | `ql_per_rupee` | 0.003872 | 0.003877 | QualLoop had lower QL/rupee than baseline_a (0.003872 vs 0.003877) |
| `delayed_conversion_trap` | `baseline_a` | `cpql` | 268.6 | 257.94 | QualLoop had higher CPQL than baseline_a (Rs 268.6 vs Rs 257.94) |
| `delayed_conversion_trap` | `baseline_a` | `false_pause_rate` | 0.0769 | 0.0 | QualLoop had higher false pause rate than baseline_a (7.69% vs 0.00%) |
| `delayed_conversion_trap` | `baseline_c` | `ql_per_rupee` | 0.003872 | 0.00395 | QualLoop had lower QL/rupee than baseline_c (0.003872 vs 0.00395) |
| `good_ad_low_reachability` | `baseline_b` | `ql_per_rupee` | 0.002819 | 0.002995 | QualLoop had lower QL/rupee than baseline_b (0.002819 vs 0.002995) |
| `high_cpql` | `baseline_b` | `ql_per_rupee` | 0.000329 | 0.000392 | QualLoop had lower QL/rupee than baseline_b (0.000329 vs 0.000392) |
| `high_cpql` | `baseline_c` | `ql_per_rupee` | 0.000329 | 0.000333 | QualLoop had lower QL/rupee than baseline_c (0.000329 vs 0.000333) |
| `mixed_portfolio` | `baseline_b` | `ql_per_rupee` | 0.004504 | 0.006742 | QualLoop had lower QL/rupee than baseline_b (0.004504 vs 0.006742) |
| `mixed_portfolio` | `baseline_b` | `missed_bad_ad_rate` | 0.1 | 0.0 | QualLoop missed more bad ads than baseline_b (10.00% vs 0.00%) |
| `mixed_portfolio` | `baseline_b` | `days_to_pause` | 16.33 | 4.1 | QualLoop took longer to pause bad ads than baseline_b (16.33d vs 4.1d) |
| `mixed_portfolio` | `baseline_a` | `false_pause_rate` | 0.05 | 0.0 | QualLoop had higher false pause rate than baseline_a (5.00% vs 0.00%) |
| `mixed_portfolio` | `baseline_c` | `qualified_leads` | 450.42 | 501.39 | QualLoop yielded fewer qualified leads than baseline_c (450.42 vs 501.39) |
| `mixed_portfolio` | `baseline_c` | `ql_per_rupee` | 0.004504 | 0.005014 | QualLoop had lower QL/rupee than baseline_c (0.004504 vs 0.005014) |
| `mixed_portfolio` | `baseline_c` | `cpql` | 222.02 | 199.45 | QualLoop had higher CPQL than baseline_c (Rs 222.02 vs Rs 199.45) |
| `mixed_portfolio` | `baseline_c` | `missed_bad_ad_rate` | 0.1 | 0.0 | QualLoop missed more bad ads than baseline_c (10.00% vs 0.00%) |
| `mixed_portfolio` | `baseline_c` | `days_to_pause` | 16.33 | 14.7 | QualLoop took longer to pause bad ads than baseline_c (16.33d vs 14.7d) |
| `small_sample_trap` | `baseline_b` | `ql_per_rupee` | 0.000667 | 0.001192 | QualLoop had lower QL/rupee than baseline_b (0.000667 vs 0.001192) |
| `small_sample_trap` | `baseline_b` | `missed_bad_ad_rate` | 1.0 | 0.0 | QualLoop missed more bad ads than baseline_b (100.00% vs 0.00%) |
| `small_sample_trap` | `baseline_c` | `missed_bad_ad_rate` | 1.0 | 0.8333 | QualLoop missed more bad ads than baseline_c (100.00% vs 83.33%) |
| `sudden_deterioration` | `baseline_b` | `ql_per_rupee` | 0.0036 | 0.003967 | QualLoop had lower QL/rupee than baseline_b (0.0036 vs 0.003967) |
