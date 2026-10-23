# QualLoop — Benchmark Methodology

**Version:** 0.1  
**Date:** 2026-10-14

---

## 1. Purpose

The benchmark demonstrates, with reproducible evidence, how QualLoop's uncertainty-aware
approach compares to a naive baseline on simulated data. Results must be based on actual
executed experiments, not hypothetical projections.

---

## 2. Baseline Policy Definition

The baseline is deliberately simple but not artificially incompetent.

### Baseline rules:

1. **Denominator:** Uses all leads, including immature ones (does not wait for maturity window)
2. **Reachability estimate:** k_contacted / n_total (raw proportion including pending leads)
3. **Qualification estimate:** k_qualified / (k_contacted or 1) — treats 0 contacts as 1 to avoid
   division by zero (silently wrong)
4. **Pending leads:** Treated the same as unresolved failures (counted in denominator)
5. **Unreachable leads:** Treated as an implicit signal of low quality (penalises qualification rate)
6. **Decision rule:** If observed qualification rate < 10% → recommend pause; else continue
7. **No credible intervals:** Point estimates only, no uncertainty representation
8. **No cooldown period:** Can recommend the same action repeatedly
9. **No maturity gate:** Fires decisions immediately when any data exists

### Why this baseline?

This represents the approach a marketing analyst might take without statistical training:
observe the raw numbers, apply a threshold, decide. It is wrong in specific, documented ways,
not because we made it bad on purpose.

---

## 3. QualLoop Policy

The QualLoop system uses:
- Beta-Binomial estimation with Beta(1,1) prior for reachability
- Beta-Binomial estimation with Beta(1,4) prior for qualification
- Maturity window gating (contact: 3 days, qualification: 7 days)
- Minimum sample thresholds (30 mature leads, 20 mature contacts)
- Credible interval-based decisions (not point estimates)
- Cooldown period of 48 simulated hours
- Explicit distinction between low reachability and low qualification

### Threshold Realism (Business Hurdle Inputs)
Thresholds such as `low_qualification_upper_bound` (e.g. 0.15) and `target_cpql` (e.g. $75.0) are **business inputs**, not learned statistical parameters. They represent the advertiser's economic breakeven requirements (unit economics, customer acquisition cost limits, sales capacity). QualLoop's statistical task is to assess whether empirical posterior evidence proves that an ad fails to meet these exogenous business hurdles, taking maturity delays and sample size into account.

---

## 4. Evaluation Metrics

All metrics are defined mathematically and conceptually prior to experiment execution.

### 4.1 False Positive Pause Rate (FPPR)

**Definition:** Fraction of truly good advertisements that were incorrectly paused by the policy.

```
FPPR = (count of genuinely good ads that were paused) / (total count of genuinely good ads)
```

- **Ground Truth:** An ad is labeled "good" by the simulator when its true intent qualification rate $q \ge 0.15$ (or configured positive target).
- **Goal:** Minimize FPPR. Prematurely pausing good ads permanently destroys conversion opportunities and campaign profitability. Target: $\text{FPPR} < 5\%$.

### 4.2 False Negative Detection Rate (FNDR) / Missed Bad Ad Rate

**Definition:** Fraction of truly poor advertisements that the policy failed to pause by the end of the evaluation window.

```
FNDR = (count of genuinely poor ads that were NOT paused) / (total count of genuinely poor ads)
```

- **Ground Truth:** An ad is labeled "bad" by the simulator when its true intent qualification rate $q \le 0.05$ (e.g. 3%–4%).
- **Goal:** Catch poor ads once sufficient evidence accumulates without guessing prematurely on noisy early data.

### 4.3 Insufficient Evidence Rate (IER)

**Definition:** The proportion of total evaluation decisions where the engine explicitly withholds a conclusive optimization action due to high statistical uncertainty or immature lead age (`collect_more_data` or `flag_insufficient_evidence`).

```
IER = (decisions with action in {collect_more_data, flag_insufficient_evidence}) / (total decisions evaluated)
```

- **Crucial Distinction:** **IER must NOT be confused with or equated to the missed-bad-ad count (FNDR).**
  - FNDR specifically evaluates poor ads that were never paused.
  - IER measures the epistemic humility of the system across the entire portfolio (good ads, bad ads, new ads). It reflects how often the system autonomously recognizes that sample size is too small or lead maturity is insufficient to justify taking an action.
  - Baselines that lack uncertainty awareness always have $\text{IER} = 0\%$, forcing premature guesses.

### 4.4 Incorrect Early Stop Rate (IESR)

**Definition:** The fraction of total portfolio advertisements that suffered an incorrect early stop (i.e. truly good ads paused prematurely).

```
IESR = (count of genuinely good ads falsely paused) / (total count of all ads evaluated)
```

- Measures portfolio-level collateral damage caused by premature pausing rules.

### 4.5 Decision Timing / Days to Correct Decision

**Definition:** For truly poor ads that are correctly paused, the elapsed simulated days from campaign start until the pause action is executed (`days_to_correct_decision`).

- **Distribution:** Tracked across checkpoints (Days 3, 7, 14, 21).
- **"Missed" Classification:** Truly poor ads that remain unpaused at the final Day 21 checkpoint are classified as "missed".
- **"Late" Metric:** For paused ads, the exact checkpoint day at which the pause occurred.

### 4.6 Spend on Truly Poor Ads Before Pause

**Definition:** Cumulative advertising budget expended on truly poor ads up to the moment they were paused (or throughout the full horizon if missed).

```
Spend_poor = \sum_{a \in \text{PoorAds}} \text{Spend accrued by ad } a \text{ up to pause day}
```

- Measures financial leakage resulting from detection delay.

### 4.7 Qualified Leads Forgone from Wrongly Paused Good Ads

**Definition:** The volume of genuine, verified qualified leads that were permanently lost because a profitable ad was erroneously killed before or during its conversion cycle.

```
Lost_QL = \sum_{a \in \text{GoodAds Falsely Paused}} \text{Qualified leads produced by } a \text{ after pause timestamp}
```

- In closed-loop sequential simulation, when an ad is paused, all future impressions, clicks, leads, and downstream qualified conversions for that ad are permanently forgone.

### 4.8 Qualified Leads Per Rupee (QL/₹) & Oracle Efficiency Ratio

**Definition:** The overall economic yield of the advertising portfolio under the policy, computed as total realized qualified leads divided by total advertising expenditure.

```
\text{QL/₹} = \frac{\text{Total Preserved Qualified Leads}}{\text{Total Cumulative Ad Spend}}
```

- **Oracle Comparison:** An omniscient Oracle that pauses all truly poor ads at Day 0 ($t=0$) while allowing all good ads to run unhindered.
- **Oracle Efficiency:** $\text{Efficiency} = \frac{\text{Policy QL/₹}}{\text{Oracle QL/₹}}$.

### 4.9 Cooldown Violations

**Definition:** For baseline policies without action memory, the frequency with which identical repetitive recommendations are emitted on the same ad within the 48-hour cooldown window.

---

## 5. Experimental Procedure

### 5.1 Simulation count

Run N = 200 independent simulation runs. Each run uses a different seed drawn from a
pre-committed seed list (stored in `benchmark/seeds.json`). Seeds are committed before
experiments run — they are not chosen after observing results.

### 5.2 Scenario distribution

Distribute 200 runs across scenario presets:

| Scenario | Count |
|----------|-------|
| healthy_campaign | 30 |
| good_ad_low_reachability | 25 |
| bad_ad_high_engagement | 25 |
| small_sample_trap | 25 |
| delayed_conversion_trap | 25 |
| creative_fatigue | 20 |
| mixed_portfolio | 20 |
| high_cpql | 15 |
| sudden_deterioration | 15 |
| **Total** | **200** |

### 5.3 Paired comparison

Each seed runs through both the baseline policy and the QualLoop policy on identical
simulated data. This ensures that observed differences are attributable to policy, not
to random variation in data.

### 5.4 Evaluation against ground truth

After each run, the benchmark module accesses the simulator's hidden ground truth to
classify ads as genuinely good or genuinely poor, then evaluates each policy's decisions
against that classification.

---

## 6. Output

Results are stored in `benchmark/results/benchmark_YYYYMMDD_HHMMSS.json` with:

```json
{
  "run_metadata": {
    "n_simulations": 200,
    "seed_file": "benchmark/seeds.json",
    "qualloop_policy_version": "v0.1.0",
    "baseline_description": "...",
    "executed_at": "2026-10-14T..."
  },
  "aggregate_metrics": {
    "qualloop": {
      "fppr_mean": 0.0,
      "fppr_ci": [0.0, 0.0],
      "fndr_mean": 0.0,
      "...": "..."
    },
    "baseline": {
      "...": "..."
    }
  },
  "per_scenario_breakdown": {...},
  "cases_where_qualloop_performed_worse": [...]
}
```

A human-readable Markdown report is generated in `benchmark/results/REPORT.md`.

---

## 7. Honesty Rules

- Results are based on actual executed runs, not projected from theory
- Cases where QualLoop performs worse are reported, not suppressed
- If the benchmark shows no improvement, the system is revised and re-run
- The final REPORT.md in the repository reflects the last actual run
- Any hardcoded benchmark numbers in the dashboard without a corresponding results file
  are prohibited
