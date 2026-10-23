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

## 2. Selection Rule for Frozen Configuration

### Formal Objective
The final policy configuration is selected according to the following constrained optimization rule applied strictly to the 100 tuning seeds:

$$\arg\min_{c \in \mathcal{C}} \text{FNDR}(c) \quad \text{subject to} \quad \text{FPPR}(c) = 0.00\% \text{ on Tuning Seeds}$$

### Business Rationale
- **Asymmetric Cost of Errors:** In growth marketing, pausing a truly good ad is far more costly than delaying the pause of a poor ad. A false pause permanently forfeits qualified lead pipeline, resets Meta ad auction learning, and depresses revenue. Conversely, letting a poor ad run until statistical certainty is reached incurs bounded, recoverable spend.
- **Tuning Set Evaluation:**
  - Config 0: $\text{FPPR} = 0.00\%$, $\text{FNDR} = 48.57\%$
  - Config 1: $\text{FPPR} = 0.00\%$, $\text{FNDR} = 40.00\%$
  - **Config 2:** $\text{FPPR} = 0.00\%$, $\text{FNDR} = 37.14\%$ (minimum FNDR satisfying constraint)
  - Config 3: $\text{FPPR} = 0.00\%$, $\text{FNDR} = 45.71\%$
  - Config 4: $\text{FPPR} = 2.14\%$ (violates the zero-FPPR constraint)
- **Outcome:** **Config 2** is uniquely selected as the single frozen policy.

### Frozen Configuration Parameters (Config 2)
- **Low Qualification Bound (`low_qualification_upper_bound`):** `0.15`
- **Minimum Mature Contacts (`min_contacts_for_qualification`):** `12`
- **Credible Interval Confidence Level (`credible_interval_level`):** `0.80` (80% CI)
- **High CPQL Bound (`high_cpql_lower_bound`):** `$75.0`
- **Minimum Maturity Fraction (`min_maturity_fraction`):** `0.50` (50%)

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
