# QualLoop vs. Naive Baseline Benchmark Report

**Executed At:** 2026-10-22T15:17:02.979855+00:00  
**Simulations:** 200  
**Total Ads Evaluated:** 350 (280 good, 70 poor)  
**QualLoop Policy:** v0.2.0  

---

## 1. Executive Summary

| Metric | QualLoop (Uncertainty-Aware) | Baseline (Naive 10% Ratio) | Delta |
|---|---|---|---|
| **False Positive Pause Rate (FPPR)** | **0.0%** [0.0%, 1.4%] | 2.1% [1.0%, 4.6%] | **-2.1%** |
| **False Negative Detection Rate (FNDR)** | **45.7%** [34.6%, 57.3%] | 7.1% [3.1%, 15.7%] | 38.6% |
| **Insufficient Evidence Rate (IER)** | 13.1% | 0.0% | +13.1% |
| **Preserved Qualified Leads** | **4417** | 5170 | +-753 |

> [!NOTE]
> **FPPR Target:** QualLoop aims for FPPR < 10%. Baseline prematurely kills good ads
> during immature windows or small sample sizes.

---

## 2. Per-Scenario Performance

| Scenario | Simulations | Ads | QualLoop FPPR | Baseline FPPR | QualLoop FNDR | Baseline FNDR |
|---|---|---|---|---|---|---|
| `bad_ad_high_engagement` | 25 | 50 | 0.0% | 0.0% | 4.0% | 0.0% |
| `creative_fatigue` | 20 | 20 | 0.0% | 0.0% | 0.0% | 0.0% |
| `delayed_conversion_trap` | 25 | 25 | 0.0% | 0.0% | 0.0% | 0.0% |
| `good_ad_low_reachability` | 25 | 50 | 0.0% | 0.0% | 0.0% | 0.0% |
| `healthy_campaign` | 30 | 90 | 0.0% | 1.1% | 0.0% | 0.0% |
| `high_cpql` | 15 | 15 | 0.0% | 6.7% | 0.0% | 0.0% |
| `mixed_portfolio` | 20 | 60 | 0.0% | 10.0% | 30.0% | 0.0% |
| `small_sample_trap` | 25 | 25 | 0.0% | 0.0% | 100.0% | 20.0% |
| `sudden_deterioration` | 15 | 15 | 0.0% | 0.0% | 0.0% | 0.0% |

---

## 3. Honesty & Transparency: Cases Where QualLoop Performed Worse

Total instances observed where QualLoop performed worse than baseline: **27**

| Scenario | Creative ID | True Intent | QualLoop Action | Baseline Action | Explanation |
|---|---|---|---|---|---|
| `bad_ad_high_engagement` | `creative_bad_hype` | 3.0% | `shift_spend` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `flag_insufficient_evidence` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `flag_insufficient_evidence` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `flag_insufficient_evidence` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
