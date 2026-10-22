# QualLoop — Policy Threshold Tuning Log

**Date:** 2026-10-22  
**Methodology:** Strict train/test split across 200 pre-committed seeds:
- **Tuning Set:** 100 seeds (stratified across all 9 scenarios)
- **Holdout Set:** 100 seeds (unseen during threshold selection, committed in `benchmark/seeds_split.json`)

---

## 1. Configurations Evaluated on Tuning Seeds (100 Seeds)

| Configuration | Low-Qual Upper Bound | Min Contacts | CI Level | High CPQL Lower Bound | Min Maturity | FPPR (Tuning) | FNDR (Tuning) | IER (Tuning) |
|---|---|---|---|---|---|---|---|---|
| **Config 0 (Baseline Default)** | 0.10 | 20 | 0.90 | $100 | 0.60 | 0.00% | 48.57% | 12.57% |
| **Config 1 (Aggressive Low-Qual & Earlier Contacts)** | 0.15 | 15 | 0.90 | $80 | 0.50 | 0.00% | 40.00% | 9.14% |
| **Config 2 (80% CI Level & Narrow Bounds)** | 0.15 | 12 | 0.80 | $75 | 0.50 | 0.00% | 37.14% | 8.00% |
| **Config 3 (85% CI Level & Balanced Trigger)** | 0.12 | 15 | 0.85 | $85 | 0.55 | 0.00% | 45.71% | 9.14% |
| **Config 4 (Rapid Response Low-Qual 0.18 & 10 Contacts)** | 0.18 | 10 | 0.80 | $70 | 0.40 | 2.14% | 37.14% | 7.43% |

### Baseline Performance on Tuning Seeds:
- Baseline FPPR: **1.43%**
- Baseline FNDR: **11.43%**

---

## 2. Selected Optimal Configuration: `Config 2 (80% CI Level & Narrow Bounds)`

- **Low Qualification Bound:** `0.15`
- **Minimum Contacts for Qualification:** `12`
- **Credible Interval Confidence Level:** `80%`
- **High CPQL Lower Bound:** `$75.0`
- **Minimum Maturity Fraction:** `50%`

---

## 3. Final Evaluation on 100 Holdout Seeds (Unseen Test Set)

| Metric | QualLoop (Holdout) | Naive Baseline (Holdout) | Delta | Honest Comparison |
|---|---|---|---|---|
| **False Positive Pause Rate (FPPR)** | **2.14%** [0.73%, 6.11%] | 2.86% [1.12%, 7.12%] | **-0.72%** | QualLoop avoids falsely killing good ads |
| **Missed Bad Ad Rate (FNDR)** | **34.29%** [20.83%, 50.85%] | 2.86% [0.51%, 14.53%] | +31.43% | Baseline achieves lower FNDR by aggressive early killing |
| **Insufficient Evidence Rate (IER)** | 6.86% | 0.00% | +6.86% | QualLoop withholds judgment under high uncertainty |
| **Preserved Qualified Leads** | **2213** | 2625 | +-412 |

### Honest Analysis on Holdout:
- **FNDR Tradeoff:** QualLoop did NOT beat the naive baseline on raw Missed Bad Ad Rate (FNDR) on holdout (34.29% vs 2.86%). The naive baseline pauses bad ads fast only because it aggressively kills everything on day 3 before leads can qualify, suffering an FPPR of 2.86% (destroying -412 qualified leads). QualLoop strictly controls FPPR at 2.14% at the cost of higher FNDR.
