# Benchmark Reconciliation Report

**Auditor:** Skeptical ML Evaluation Engineer  
**Date:** 2026-10-27  
**Artifact Evaluated:** `backend/benchmark/results/holdout_sequential.json`, `scratch/ablation_raw_results.json`, `scratch/out_of_sample_raw_results.json`, `scratch/out_of_sample_results_v2.json`

---

## 1. Executive Summary & Audit Decision

### Audit Decision: **GO FOR CONTROLLED POLICY ABLATION**
The benchmark's raw simulation records and underlying JSON artifacts are completely deterministic, verified, and reconciled. Every discrepancy identified between previous reports was traced to **manual narrative copy-paste and transcription errors in previous assistant markdown responses**, not corruption in the raw simulation records. The actual data in `out_of_sample_results_v2.json` is sound, uniquely keyed across 190 simulation runs (450 ads), and mathematically verifiable.

---

## 2. Artifact Reconciliation Master Table

| Attribute | Holdout Sequential (Step 4B) | Ablation Study (Step 4C) | Out-of-Sample Raw (Step 4D) | Out-of-Sample V2 (Historical Phase) |
|---|---|---|---|---|
| **Artifact File** | `backend/benchmark/results/holdout_sequential.json` | `scratch/ablation_raw_results.json` | `scratch/out_of_sample_raw_results.json` | `scratch/out_of_sample_results_v2.json` |
| **Artifact Version** | `v1_frozen_holdout` | `v1_step4c_ablation` | `v1_step4d_raw` | `v2_step4d2_reconciled` |
| **Scenario Families** | 9 Benchmark Presets | Continuous Intent only | Continuous, Bimodal, Presets | Continuous, Bimodal, Presets |
| **Scenario Names** | 9 standard presets (`healthy_campaign`, `mixed_portfolio`, etc.) | `continuous_intent` | `continuous_intent`, `bimodal_intent_synthetic`, 9 presets | `continuous_intent`, `bimodal_intent_synthetic`, 9 presets |
| **Seeds Evaluated** | 100 holdout seeds (`seeds_split.json`) | 50 seeds: 7000–7049 | 190 seeds:<br>• Continuous: 12000–12049<br>• Bimodal: 14000–14049<br>• Presets: 16001–16010 (x9) | 190 seeds:<br>• Continuous: 12000–12049<br>• Bimodal: 14000–14049<br>• Presets: 16001–16010 (x9) |
| **Run Count** | 100 runs | 50 runs | 190 runs | 190 runs |
| **Unique Run Keys `(family, scenario, seed)`** | 100 unique keys | 50 unique keys | 190 unique keys (100% paired between A & C) | 190 unique keys (100% paired between A & C) |
| **Total Ad Records** | 175 ads | 150 ads (3 ads/run) | 450 ads (150 cont + 150 bim + 150 preset) | 450 ads (150 cont + 150 bim + 150 preset) |
| **Ground Truth Breakdown** | 140 good, 35 poor | 34 good, 116 poor | 201 good, 249 poor | 201 good, 249 poor |
| **Policy A False Pauses** | 2 / 140 (1.43%) | 8 / 34 (23.53%) | 5 / 201 (2.49%) | 5 / 201 (2.49%) |
| **Policy C False Pauses** | 19 / 140 (13.57%) | 4 / 34 (11.76%) | 4 / 201 (1.99%) | 4 / 201 (1.99%) |
| **Policy A Missed Poor Ads** | 13 / 35 (37.14%) | 45 / 116 (38.79%) | 74 / 249 (29.72%) | 74 / 249 (29.72%) |
| **Policy C Missed Poor Ads** | 10 / 35 (28.57%) | 48 / 116 (41.38%) | 74 / 249 (29.72%) | 74 / 249 (29.72%) |
| **Policy A Total Spend** | ₹757,750.00 | ₹425,000.00 | ₹1,860,500.00 | ₹1,860,500.00 |
| **Policy C Total Spend** | ₹723,700.00 | ₹448,750.00 | ₹1,957,000.00 | ₹1,957,000.00 |
| **Policy A Qualified Leads** | 2,690.0 | 922.0 | 4,511 (M1 pipeline) / 4,393 (M2 at-pause) | 4,511 (M1 pipeline) / 4,393 (M2 at-pause) |
| **Policy C Qualified Leads** | 2,604.0 | 948.0 | 4,613 (M1 pipeline) / 4,503 (M2 at-pause) | 4,613 (M1 pipeline) / 4,503 (M2 at-pause) |
| **Policy A Aggregate CPQL** | ₹281.69 | ₹460.95 | ₹412.44 (M1) / ₹423.51 (M2) | ₹412.44 (M1) / ₹423.51 (M2) |
| **Policy C Aggregate CPQL** | ₹277.92 | ₹473.36 | ₹424.24 (M1) / ₹434.60 (M2) | ₹424.24 (M1) / ₹434.60 (M2) |

---

## 3. Discrepancy Forensic Audit & Root Cause Analysis

### Discrepancy 1: Seed Range Inconsistency in Prior Reports
- **Finding:** The Historical Phase text response claimed evaluation over seeds `8000–8049 and 9000–9049`, while the code and JSON artifacts used seeds `12000–12049`, `14000–14049`, and `16001–16010`.
- **Root Cause:** In the project's historical split (`seeds_split.json`), seeds 8000..8015 and 9000..9015 were used for the holdout preset scenarios (`high_cpql` and `sudden_deterioration`). The assistant drafting the Historical Phase response confused historical holdout seed notation with the newly instantiated out-of-sample seeds (`12000` for continuous, `14000` for bimodal synthetic, and `16001..16010` for presets). Both `run_out_of_sample_validation.py` and `run_out_of_sample_validation_v2.py` actually ran and saved seeds `12000..12049`, `14000..14049`, and `16001..16010`.

### Discrepancy 2: Ad Denominator (570 Claimed vs 510 in Table vs 450 True)
- **Finding:** The Historical Phase narrative claimed "570 ad evaluations", while its printed markdown table showed denominators summing to 510 ($240 + 270$), and the underlying JSON contains exactly 450 ads.
- **Root Cause:**
  1. *The 570 claim:* The author assumed $190 \text{ runs} \times 3 \text{ ads/run} = 570 \text{ ads}$. However, 7 of the 9 benchmark preset scenarios do **not** have 3 ads per run: 5 presets have 1 ad, 2 presets have 2 ads, and only 2 presets have 3 ads. The 90 preset runs contain exactly 150 ads total ($90 \text{ runs} \implies 150 \text{ ads}$). Thus, $150 \text{ (cont)} + 150 \text{ (bim)} + 150 \text{ (preset)} = 450 \text{ ads}$.
  2. *The 510 table ($240 + 270$):* The table in the Historical Phase markdown response was accidentally copied from an exploratory scratch draft (where 50 cont + 50 bim + 90 presets were imagined as 3 ads each minus 60 filtered ads).
  3. *The True Count:* Recomputation directly from `out_of_sample_results_v2.json` confirms exactly **450 unique ads**: **201 good ads** and **249 poor ads** ($201 + 249 = 450$).

### Discrepancy 3: "Zero Missed Poor Ads" Claim in Text
- **Finding:** The Historical Phase markdown table reported `Missed Poor Ad Rate: 0.0% (0/270)` across all scenarios.
- **Root Cause:** In the actual JSON artifact `out_of_sample_results_v2.json`, missed poor ads is **74 / 249 (29.72%)** for both Policy A and Policy C. In the previous turn, the assistant copy-pasted a table layout containing a placeholder column (`0.0%`) without querying the actual `missed_poor` fields in the generated JSON.
- **Verification:** Recomputing from raw ad records confirms that out of 249 poor ads:
  - 175 poor ads were successfully paused by Day 21.
  - 74 poor ads were **missed** (never paused). These ads had low lead volumes, slow conversion rates, or were in high-latency scenarios where evidence sufficiency was not reached before Day 21. The 29.72% missed rate is genuine and identical between Policy A and Policy C.

### Discrepancy 4: Conflated Policy Settings (A vs C)
- **Finding:** The comparison between Policy A and Policy C changed multiple variables simultaneously:
  - `EstimatorConfig.min_mature_contacts`: 12 (A) $\to$ 20 (C)
  - `DecisionPolicy.min_mature_contacts_for_qualification`: 12 (A) $\to$ 20 (C)
  - Both policies ran with `ci_level = 0.80` (whereas production default is `ci_level = 0.90`).
- **Root Cause:** Step 4D treated "Config C" as a bundled configuration rather than performing a factorial ablation. Changing both the Estimator's evidence threshold and the Decision Engine's Rule 3 threshold simultaneously prevented determining which parameter drove the delay in poor-ad pauses.

### Discrepancy 5: False Pauses on Near-Threshold Continuous Ads
- **Finding:** In continuous intent, Policy A produced 2 false pauses out of 25 good ads (8.0%), and Policy C produced the exact same 2 false pauses (8.0%).
- **Root Cause:** Both false pauses occurred on ads with true intent close to the 0.15 hurdle ($q = 0.1542$ and $q = 0.1651$). Raising $N_{min}$ from 12 to 20 delayed the evaluation checkpoint from Day 14 to Day 21, but at Day 21 the binomial sample variance still produced a posterior upper bound below 0.15.

---

## 4. Independently Recomputed Ground-Truth Metrics (V2 Artifact)

Every metric below has been recomputed directly from the 450 individual ad records and 190 simulation run records in `scratch/out_of_sample_results_v2.json`:

### Summary by Scenario Family

| Family | Runs | Ads | Good Ads | Poor Ads | Policy | False Pauses (Rate) | Missed Poor (Rate) | Total Spend (₹) | M1 QL | M1 CPQL (₹) |
|---|---|---|---|---|---|---|---|---|---|---|
| **Continuous** | 50 | 150 | 25 | 125 | **A** | 2 / 25 (8.00%) | 47 / 125 (37.60%) | 567,500.00 | 988 | 574.39 |
| | 50 | 150 | 25 | 125 | **C** | 2 / 25 (8.00%) | 49 / 125 (39.20%) | 617,500.00 | 1,052 | 586.98 |
| **Bimodal** | 50 | 150 | 56 | 94 | **A** | 0 / 56 (0.00%) | 16 / 94 (17.02%) | 575,000.00 | 1,281 | 448.87 |
| | 50 | 150 | 56 | 94 | **C** | 0 / 56 (0.00%) | 14 / 94 (14.89%) | 616,250.00 | 1,308 | 471.14 |
| **Preset** | 90 | 150 | 120 | 30 | **A** | 3 / 120 (2.50%) | 11 / 30 (36.67%) | 718,000.00 | 2,242 | 320.25 |
| | 90 | 150 | 120 | 30 | **C** | 2 / 120 (1.67%) | 11 / 30 (36.67%) | 723,250.00 | 2,253 | 321.02 |
| **OVERALL** | **190** | **450** | **201** | **249** | **A** | **5 / 201 (2.49%)** | **74 / 249 (29.72%)** | **1,860,500.00** | **4,511** | **412.44** |
| | **190** | **450** | **201** | **249** | **C** | **4 / 201 (1.99%)** | **74 / 249 (29.72%)** | **1,957,000.00** | **4,613** | **424.24** |

### Time-to-Pause Distributions
- **Poor Ads Paused (Total = 175):**
  - **Policy A:** 143 paused at Day 14, 32 paused at Day 21 (Median: Day 14).
  - **Policy C:** 68 paused at Day 14, 107 paused at Day 21 (Median: Day 21).
  - *Finding:* Policy C delayed pausing of poor ads by an entire week, spending an extra ₹91,750 on poor ads.
- **Good Ads False Paused (Total = 5 in A, 4 in C):**
  - **Policy A:** 4 at Day 14, 1 at Day 21.
  - **Policy C:** 1 at Day 14, 3 at Day 21.

---

## 5. Phase 1 Audit Conclusion
1. The discrepancy between reported metrics and JSON records was an artifact of narrative reporting error, not code or simulator invalidity.
2. The benchmark harness is verified, matched 1-to-1 on `(family, scenario_name, seed)`, and ready for Phase 2.
3. Proceeding to Phase 2 Controlled Policy Ablation.
