# QualLoop vs. Naive Baseline Benchmark Report

**Executed At:** 2026-10-22T06:47:55.282054+00:00  
**Simulations:** 45  
**Total Ads Evaluated:** 75 (60 good, 15 poor)  
**QualLoop Policy:** v0.1.0  

---

## 1. Executive Summary

| Metric | QualLoop (Uncertainty-Aware) | Baseline (Naive 10% Ratio) | Delta |
|---|---|---|---|
| **False Positive Pause Rate (FPPR)** | **0.0%** [0.0%, 6.0%] | 1.7% [0.3%, 8.9%] | **-1.7%** |
| **False Negative Detection Rate (FNDR)** | **40.0%** [19.8%, 64.3%] | 20.0% [7.0%, 45.2%] | 20.0% |
| **Insufficient Evidence Rate (IER)** | 12.0% | 0.0% | +12.0% |
| **Preserved Qualified Leads** | **947** | 1096 | +-149 |

> [!NOTE]
> **FPPR Target:** QualLoop aims for FPPR < 10%. Baseline prematurely kills good ads
> during immature windows or small sample sizes.

---

## 2. Per-Scenario Performance

| Scenario | Simulations | Ads | QualLoop FPPR | Baseline FPPR | QualLoop FNDR | Baseline FNDR |
|---|---|---|---|---|---|---|
| `bad_ad_high_engagement` | 5 | 10 | 0.0% | 0.0% | 20.0% | 0.0% |
| `creative_fatigue` | 5 | 5 | 0.0% | 0.0% | 0.0% | 0.0% |
| `delayed_conversion_trap` | 5 | 5 | 0.0% | 0.0% | 0.0% | 0.0% |
| `good_ad_low_reachability` | 5 | 10 | 0.0% | 0.0% | 0.0% | 0.0% |
| `healthy_campaign` | 5 | 15 | 0.0% | 6.7% | 0.0% | 0.0% |
| `high_cpql` | 5 | 5 | 0.0% | 0.0% | 0.0% | 0.0% |
| `mixed_portfolio` | 5 | 15 | 0.0% | 0.0% | 0.0% | 0.0% |
| `small_sample_trap` | 5 | 5 | 0.0% | 0.0% | 100.0% | 60.0% |
| `sudden_deterioration` | 5 | 5 | 0.0% | 0.0% | 0.0% | 0.0% |

---

## 3. Honesty & Transparency: Cases Where QualLoop Performed Worse

Total instances observed where QualLoop performed worse than baseline: **3**

| Scenario | Creative ID | True Intent | QualLoop Action | Baseline Action | Explanation |
|---|---|---|---|---|---|
| `bad_ad_high_engagement` | `creative_bad_hype` | 3.0% | `continue_monitoring` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
| `small_sample_trap` | `creative_new_bad` | 4.0% | `collect_more_data` | `consider_pause` | QualLoop was too conservative to pause a poor ad |
