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

---

## 4. Evaluation Metrics

All metrics are defined precisely before any experiment runs.

### 4.1 False Positive Pause Rate (FPPR)

**Definition:** Fraction of simulation runs where the system recommended pausing (or considered
pausing) a genuinely good ad.

A "genuinely good ad" is defined as one where the simulator's hidden true qualification rate
is above the portfolio median.

```
FPPR = (runs where good ad received consider_pause) / (total runs where good ad existed)
```

Lower is better. QualLoop target: FPPR < 0.10 (vs baseline expected > 0.25 in small-sample scenarios).

### 4.2 False Negative Detection Rate (FNDR)

**Definition:** Fraction of simulation runs where the system failed to recommend any action for
a genuinely poor ad after the maturity window elapsed.

A "genuinely poor ad" is defined as one where the simulator's hidden true qualification rate
is below 0.05 (5%).

```
FNDR = (runs where poor ad received no action after maturity) / (total runs with poor ad)
```

Lower is better. High FNDR means the system is too conservative. High FPPR means it acts too fast.

### 4.3 Decision Timing

**Definition:** For correctly identified poor ads, the simulated days elapsed before
the first `consider_pause` or stronger recommendation.

**Reported as:** Median and IQR of simulated days across qualifying simulation runs.

### 4.4 Qualified Leads per Unit Spend (QLUS)

**Definition:** Across the full benchmark, the total estimated qualified leads divided by
total simulated spend, for each policy.

This captures whether the policy efficiently identifies and preserves good ads while
flagging poor ones.

### 4.5 Insufficient Evidence Rate (IER)

**Definition:** Fraction of decisions that were `flag_insufficient_evidence` or
`collect_more_data` when the sample was actually mature.

Measures whether the system is correctly cautious vs needlessly timid.

### 4.6 Cooldown Violations

Applies to baseline only: how often the baseline fires the same recommendation within
48 hours of a prior recommendation on the same ad.

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
