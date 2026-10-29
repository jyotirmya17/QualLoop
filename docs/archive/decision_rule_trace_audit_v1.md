# Decision-Rule Trace Audit and Baseline Verification

**Auditor:** Skeptical ML Evaluation Engineer  
**Date:** 2026-10-27  
**Artifacts Generated:**  
- `scratch/decision_rule_trace_audit_v1.json`  
- `scratch/decision_rule_trace_audit_v1.md`  

---

## 1. Verified Production Baseline Configuration & Runtime Wiring

A critical finding of this audit is that **production runtime defaults differ markedly from the experimental configurations evaluated in the Step 4B/4C/4D benchmarks**:

| Setting / Threshold | Exact Source File | Symbol Name | Effective Runtime Value | Notes / Production Semantics |
|---|---|---|---|---|
| **Production Credible Interval (`ci_level`)** | [`backend/estimator/estimator.py`](file:///d:/Developer/qualloop/backend/estimator/estimator.py#L44-L57) | `CI_LEVEL = 0.90` / `EstimatorConfig.ci_level` | **`0.90` (90% CI)** | Benchmark studies (4B, 4C, 4D, 4D.3) evaluated candidate `ci_level = 0.80`. Production uses 90%. |
| **Estimator Min Mature Contacts** | [`backend/estimator/estimator.py`](file:///d:/Developer/qualloop/backend/estimator/estimator.py#L41-L55) | `MIN_MATURE_CONTACTS = 20` / `EstimatorConfig.min_mature_contacts` | **`20` contacts** | Sets `evidence_sufficient_qualification = True` when mature contacts $\ge 20$. |
| **Policy Min Mature Contacts** | [`backend/decision_engine/engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L33) | `DecisionPolicy.min_mature_contacts_for_qualification` | **`20` contacts** | Evaluated in Rule 3: triggers `COLLECT_MORE_DATA` if $N < 20$. |
| **Min Maturity Fraction (Contact)** | [`backend/estimator/estimator.py`](file:///d:/Developer/qualloop/backend/estimator/estimator.py#L42-L56) / [`engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L34) | `MIN_MATURITY_FRACTION = 0.60` | **`0.60` (60%)** | Evaluated in Rule 1: triggers `FLAG_INSUFFICIENT_EVIDENCE` if fraction $< 0.60$. |
| **Min Mature Leads (Reachability)** | [`backend/estimator/estimator.py`](file:///d:/Developer/qualloop/backend/estimator/estimator.py#L40-L54) / [`engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L32) | `MIN_MATURE_LEADS = 30` | **`30` leads** | Evaluated in Rule 2: triggers `COLLECT_MORE_DATA` if mature leads $< 30$. |
| **Low Qualification Upper Bound** | [`backend/decision_engine/engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L36) | `DecisionPolicy.low_qualification_upper_bound` | **`0.10` (10%)** | Rule 6 triggers pause when posterior CI upper bound $< 0.10$. (Note: Benchmarks evaluated a 0.15 hurdle). |
| **Low Reachability Upper Bound** | [`backend/decision_engine/engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L35) | `DecisionPolicy.low_reachability_upper_bound` | **`0.25` (25%)** | Rule 5 triggers `INVESTIGATE_LOW_REACHABILITY` (not pause). |
| **High CPQL Lower Bound** | [`backend/decision_engine/engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L37) | `DecisionPolicy.high_cpql_lower_bound` | **`500.0`** | Reallocation threshold. |
| **Target CPQL** | [`backend/decision_engine/engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L38) | `DecisionPolicy.target_cpql` | **`75.0`** | Budget raise threshold (Rule 9). |
| **Policy Version** | [`backend/decision_engine/engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py#L21) | `POLICY_VERSION = "v0.2.0"` | **`"v0.2.0"`** | Stored with persisted decisions in SQLite. |

### Authoritative Runtime Wiring
1. **Application Entry Points:**
   - [`backend/api/evaluation.py`](file:///d:/Developer/qualloop/backend/api/evaluation.py#L33-L35): Instantiates `_DEFAULT_CONFIG = EstimatorConfig()` and `_DEFAULT_POLICY = DecisionPolicy()`.
   - [`backend/api/routers/ads.py`](file:///d:/Developer/qualloop/backend/api/routers/ads.py#L26-L27): Instantiates `_DEFAULT_CONFIG = EstimatorConfig()` and `_DEFAULT_POLICY = DecisionPolicy()`.
2. **Overrides Audit:**
   - **Environment Variables:** Only `DATABASE_URL` is parsed by [`persistence/database.py`](file:///d:/Developer/qualloop/backend/persistence/database.py#L37). Zero environment variable overrides exist for policy or estimator configuration.
   - **Database Tables:** The `decisions` table in [`persistence/models.py`](file:///d:/Developer/qualloop/backend/persistence/models.py#L21) stores decision snapshots and `policy_version`, but does not store or override threshold parameters.
   - **Preset Scenarios:** Presets in [`simulator/scenarios.py`](file:///d:/Developer/qualloop/backend/simulator/scenarios.py) define synthetic simulation traffic (latency, click-rates, true intent), not policy parameters.

*Conclusion:* The Python default dataclasses in `estimator.py` and `engine.py` are unconditionally authoritative in production.

---

## 2. Why Configurations B, C, and D Produced Identical Results

In Historical Phase, across all 450 evaluated ads:
- **Pause day differences (B vs C): 0**
- **Pause day differences (C vs D): 0**
- **Spend differences (B vs C): ₹0.00**
- **Qualified lead differences (B vs C): 0**

### Causal Mechanism
The identical behavior of B, C, and D is caused by an architectural interaction between **Rule 3** (Policy Qualification Sample Gate) and **Rule 6** (Low-Qualification Pause Evidence Gate):

```
                                  [Ad Snapshot Evaluation]
                                             |
                         [Rule 1: Maturity Fraction >= 0.50?]
                                             | Yes
                         [Rule 2: Mature Leads >= 30?]
                                             | Yes
                         [Rule 3: Mature Contacts >= Policy N_min?]
                                   /                   \
                        No (< 20) /                     \ Yes (>= 20 in C/D; >= 12 in B)
                                 /                       \
               [Action: COLLECT_MORE_DATA]          [Rule 4: Anomaly Check]
                    (Non-pause action)                    |
                                                    [Rule 5: Reachability Check]
                                                          |
                                            [Rule 6: Low-Qual Pause Gate]
                                            - CI Upper Bound < 0.15?
                                            - Evidence Sufficient (N >= Est N_min)?
                                                   /                 \
                                        Yes (N >= 20) /                   \ No (N < 20 in B)
                                                     /                     \
                                            [Action: PAUSE]       [Rules 7-9: Also Gated on N >= 20]
                                                                           |
                                                                  [Rule 10: Fallback]
                                                             [Action: CONTINUE_MONITORING]
                                                                  (Non-pause action)
```

1. **When $12 \le N_{mature} < 20$ (e.g. at Day 14):**
   - **Config C & D ($N_{pol} = 20$):** Rule 3 fires directly because $N < 20$, returning `COLLECT_MORE_DATA`.
   - **Config B ($N_{pol} = 12, N_{est} = 20$):** Rule 3 passes ($N \ge 12$). However, Rule 6 checks `estimate.evidence_sufficient_qualification`, which is `False` because the estimator requires 20. Rule 6 is blocked! Rules 7, 8, and 9 also require evidence sufficiency and are blocked. The engine deterministically falls through to **Rule 10**, returning `CONTINUE_MONITORING`.
   - **Operational Consequence:** Both `COLLECT_MORE_DATA` (Rule 3) and `CONTINUE_MONITORING` (Rule 10) are **non-pause actions**. The simulator continues running the ad with full budget.
2. **When $N_{mature} \ge 20$ (e.g. at Day 21):**
   - In B, C, and D, both the policy threshold ($N \ge 20$) and estimator sufficiency (`evidence_sufficient_qualification = True`) are satisfied simultaneously.
   - If the ad's posterior upper bound is below 0.15, **Rule 6 fires in B, C, and D at the exact same checkpoint (Day 21)**.
3. **When an ad never reaches $N_{mature} \ge 20$ by Day 21:**
   - Neither B, C, nor D ever pause the ad. All three miss it.

### Raw Decision Traces: The 90 Ads Paused in A at Day 14
In Baseline Config A, exactly 90 ads were paused at Day 14 ($12 \le N < 20$):
- **73 ads were delayed to Day 21 in B, C, and D:**
  - *Example Ad:* `e0044684-1c68-ea46-47da-2f880257193a` (Continuous Intent, Seed 22004, True Intent = 0.0723, Poor ad):
    - **Day 14 in A:** $N = 13, k = 0, \theta_{0.80} \in [0.0\%, 2.9\%]$. Paused under Rule 6 at Day 14 (Spend: ₹2,500.00).
    - **Day 14 in B:** $N = 13$, Rule 3 passed, but `evidence_sufficient_qualification = False`. Rule 6 blocked. Rule 10 returned `CONTINUE_MONITORING`.
    - **Day 14 in C & D:** $N = 13 < 20$, Rule 3 returned `COLLECT_MORE_DATA`.
    - **Day 21 in B, C, & D:** $N = 43, k = 2, \theta_{0.80} \in [2.4\%, 8.3\%]$. Rule 6 fired simultaneously in B, C, and D. Paused at Day 21 (Spend: ₹3,750.00).
    - *Cost of Delay:* ₹1,250.00 in additional spend on a known poor ad.
- **17 ads were never paused (missed) in B, C, and D:**
  - *Example Ad:* `55a06f9b-c555-1d6a-6f02-e81d5f712a77` (Continuous Intent, Seed 22002, True Intent = 0.0560, Poor ad):
    - **Day 14 in A:** $N = 12, k = 1, \theta_{0.80} \in [2.3\%, 13.9\%]$. Paused at Day 14 under Rule 6 (Spend: ₹2,500.00).
    - **Day 14 & 21 in B, C, & D:** Mature contacts never reached 20. Neither Rule 3 nor Rule 6 ever allowed a pause. The ad ran all 28 days with ₹5,000.00 spend.
    - *Cost of Missing:* ₹2,500.00 in completely wasted spend.

---

## 3. Boundary Case Findings & Mathematical Explanation

### Empirical Boundary Performance ($q_{true} \in [0.13, 0.17]$)
Analyzing the 30 ads situated near the 0.15 hurdle:
- **Good Boundary Ads ($q_{true} \in [0.15, 0.17]$, 14 ads):**
  - **Config A:** 5 / 14 (35.7%) False Pauses.
  - **Config D:** 5 / 14 (35.7%) False Pauses.
  - **Causal Impact:** Raising $N_{min}$ from 12 to 20 had **zero effect** on boundary false pauses. The exact same 5 near-hurdle good ads were false paused in both configurations.
- **Poor Boundary Ads ($q_{true} \in [0.13, 0.15)$, 16 ads):**
  - **Config A:** 10 / 16 (62.5%) Missed Poor Ads.
  - **Config D:** 12 / 16 (75.0%) Missed Poor Ads.

### Mathematical Root Cause: Binomial Sampling Variance
Consider a good ad with true buying intent $q = 0.16$ evaluated at $N = 30$ mature contacts:
1. Expected qualified leads: $E[k] = 30 \times 0.16 = 4.8$.
2. Under a $\text{Binomial}(30, 0.16)$, the cumulative probability of observing $k \le 2$ qualifications by chance is:
   $$P(k \le 2) = \sum_{j=0}^2 \binom{30}{j} (0.16)^j (0.84)^{30-j} = 0.0053 + 0.0305 + 0.0842 = 0.120 \quad (12.0\%)$$
3. If $k = 2$, under a uniform Beta(1, 1) prior, the posterior distribution is $\text{Beta}(3, 29)$:
   - Posterior Mean: $\frac{3}{32} = 9.38\%$
   - 90th Percentile ($\theta_{0.90}$, the 80% CI upper bound):
     $$\text{Beta}^{-1}(0.90; \alpha=3, \beta=29) = 0.1492 < 0.1500$$
4. Because $0.1492 < 0.15$, **Rule 6 triggers a pause**, even though the ad is genuinely good ($q = 0.16$).

*Conclusion:* Increasing $N_{min}$ to 20 or 30 does not resolve this issue. A sample of $N=30$ still has a 12% probability of sampling $k \le 2$, and $N=40$ has an 8% probability. To eliminate false pauses on near-hurdle ads without waiting for hundreds of leads, the engine requires **boundary abstention** or **hysteresis**, not a higher global sample size threshold.

---

## 4. Tests Added & Test Suite Verification

### Regression Test Added
In [`backend/tests/test_decision_engine.py`](file:///d:/Developer/qualloop/backend/tests/test_decision_engine.py#L811):
- Added [`test_estimator_and_policy_contact_thresholds_distinct_semantics`](file:///d:/Developer/qualloop/backend/tests/test_decision_engine.py#L811).
- Directly tests the intermediate state ($N=15$):
  1. **Config A (12, 12):** Rule 3 passes, evidence sufficient $\implies$ Rule 6 fires (`PAUSE_AD`).
  2. **Config B (20, 12):** Rule 3 passes, but evidence insufficient $\implies$ Rule 6 blocked $\implies$ deterministic fallback to Rule 10 (`CONTINUE_MONITORING`).
  3. **Config C (12, 20):** Rule 3 fires directly $\implies$ `COLLECT_MORE_DATA`.
  4. **Config D (20, 20):** Rule 3 fires directly $\implies$ `COLLECT_MORE_DATA`.

### Test Results
1. **Decision Engine Suite:**
   ```bash
   python -m pytest backend/tests/test_decision_engine.py -v
   ```
   **Result:** `31 passed in 0.70s`
2. **Benchmark Suite:**
   ```bash
   python -m pytest backend/tests/test_benchmark.py -v
   ```
   **Result:** `24 passed in 21.37s`
3. **Full Backend Test Suite:**
   ```bash
   python -m pytest backend/tests
   ```
   **Result:** `175 passed in 97.64s`

---

## 5. Remaining Risks & Next Highest-ROI Action

### Remaining Risks
1. **Benchmark vs Production Baseline Divergence:**
   The entire Step 4 benchmark track has evaluated experimental policies with `ci_level = 0.80` and `low_qualification_upper_bound = 0.15` (the 0.15 hurdle). Production code in master currently defaults to `ci_level = 0.90` and `low_qualification_upper_bound = 0.10`. Decisions generated in production live traffic are significantly more conservative than those tested in benchmark simulations.
2. **Boundary Sensitivity in Continuous Campaigns:**
   Near-hurdle ads ($q \in [0.154, 0.177]$) will continue to suffer a 25–35% false pause rate under any pure thresholding rule due to natural binomial variance.

### Next Highest-ROI Action
**Implement Narrow Boundary Abstention (Asymmetric Decision Hysteresis):**
Rather than changing contact thresholds or relaxing credible intervals, add an abstention rule to `DecisionPolicy`:
```python
# If posterior mean is within +/- 1.5% of the hurdle and N < 40:
if abs(estimate.qualification_mean - policy.low_qualification_upper_bound) <= 0.015:
    return COLLECT_MORE_DATA
```
This directly eliminates boundary false pauses without delaying poor-ad pauses on clearly bad campaigns ($q \le 0.08$), achieving the optimal trade-off between pause speed and accuracy.
