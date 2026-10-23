# QualLoop vs. Naive Baseline Benchmark Report

**Executed At:** 2026-10-23T03:30:37.207908+00:00  
**Simulations:** 100  
**Total Ads Evaluated:** 175 (140 good, 35 poor)  
**QualLoop Policy:** v0.2.0  

---

## 1. Executive Summary

| Metric | QualLoop (Uncertainty-Aware) | Baseline (Naive 10% Ratio) | Delta |
|---|---|---|---|
| **False Positive Pause Rate (FPPR)** | **0.0%** [0.0%, 2.7%] | 2.9% [1.1%, 7.1%] | **-2.9%** |
| **False Negative Detection Rate (FNDR)** | **42.9%** [28.0%, 59.1%] | 2.9% [0.5%, 14.5%] | 40.0% |
| **Insufficient Evidence Rate (IER)** | 13.7% | 0.0% | +13.7% |
| **Incorrect Early Stop Rate (IESR)** | 0.0% | 2.3% | -2.3% |
| **Preserved Qualified Leads** | **2237** | 2625 | +-388 |

> [!NOTE]
> **FPPR Target:** QualLoop aims for FPPR < 10%. Baseline prematurely kills good ads
> during immature windows or small sample sizes.

---

## 2. Per-Scenario Performance

| Scenario | Simulations | Ads | QualLoop FPPR | Baseline FPPR | QualLoop FNDR | Baseline FNDR |
|---|---|---|---|---|---|---|
| `bad_ad_high_engagement` | 13 | 26 | 0.0% | 0.0% | 0.0% | 0.0% |
| `creative_fatigue` | 10 | 10 | 0.0% | 0.0% | 0.0% | 0.0% |
| `delayed_conversion_trap` | 13 | 13 | 0.0% | 0.0% | 0.0% | 0.0% |
| `good_ad_low_reachability` | 12 | 24 | 0.0% | 0.0% | 0.0% | 0.0% |
| `healthy_campaign` | 15 | 45 | 0.0% | 0.0% | 0.0% | 0.0% |
| `high_cpql` | 7 | 7 | 0.0% | 14.3% | 0.0% | 0.0% |
| `mixed_portfolio` | 10 | 30 | 0.0% | 15.0% | 30.0% | 0.0% |
| `small_sample_trap` | 12 | 12 | 0.0% | 0.0% | 100.0% | 8.3% |
| `sudden_deterioration` | 8 | 8 | 0.0% | 0.0% | 0.0% | 0.0% |

---

## 3. Honesty & Transparency: Cases Where QualLoop Performed Worse

Total instances observed where QualLoop performed worse than baseline: **14**

| Scenario | Creative ID | True Intent | QualLoop Action | Baseline Action | Explanation |
|---|---|---|---|---|---|
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `mixed_portfolio` | `creative_poor` | 4.0% | `shift_spend` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `mixed_portfolio` | `creative_poor` | 4.0% | `shift_spend` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `mixed_portfolio` | `creative_poor` | 4.0% | `shift_spend` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
