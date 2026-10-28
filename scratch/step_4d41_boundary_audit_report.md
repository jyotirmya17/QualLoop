# Step 4D.4.1 — Correct the Boundary-Rule Proposal & Production Baseline Evaluation

**Role:** Skeptical ML Evaluation Engineer  
**Date:** 2026-10-28  
**Audit Scope:** Audit only. No production code modified; no git commits created.  
**Preserved Artifacts:**  
- `scratch/evaluate_step_4d41.py`
- `scratch/step_4d41_evaluation_results.json`
- `scratch/print_cis.py`
- `scratch/step_4d41_boundary_audit_report.md`

---

## 1. Mathematical Verification & Correction of the Proposed Boundary Rule

### 1.1 The Prior Report's Example
In the Step 4D.4 trace report (`decision_rule_trace_audit_v1.json` / `.md`), the false-pause example was stated as:
> *"Under Binomial(30, 0.16), $P(k \le 2) = 11.5\%$. For $k=2$, $\text{Beta}(3, 29)$ has $\theta_{0.90} = 0.149 < 0.15$, triggering Rule 6 false pause."*

The author subsequently proposed a boundary abstention condition (hysteresis):
```python
# Proposed in Step 4D.4:
if abs(estimate.qualification_mean - policy.low_qualification_upper_bound) <= 0.015:
    return COLLECT_MORE_DATA
```

### 1.2 Mathematical Dissection & Prior Error Correction
1. **Flawed Posterior Notation ($\text{Beta}(3, 29)$ vs $\text{Beta}(3, 32)$):**
   - The report assumed a flat $\text{Beta}(1, 1)$ prior ($\alpha_0 = 1, \beta_0 = 1$). Under that prior, $k=2$ successes and $N-k = 28$ failures would produce $\text{Beta}(1+2, 1+28) = \text{Beta}(3, 29)$.
   - However, for $\text{Beta}(3, 29)$, the posterior 90th percentile is $\text{Beta}^{-1}(0.90; 3, 29) = \mathbf{0.1627}$ ($16.27\%$). Since $16.27\% > 15\%$, **an ad with $\text{Beta}(3, 29)$ would NEVER have been paused by Rule 6**!
   - In the actual QualLoop implementation ([`backend/estimator/estimator.py:36-37`](file:///d:/Developer/qualloop/backend/estimator/estimator.py#L36-L37)):
     $$\alpha_0 = 1.0, \quad \beta_0 = 4.0 \quad (\text{encodes a } 20\% \text{ prior mean})$$
     $$\alpha_{\text{post}} = 1 + 2 = 3, \quad \beta_{\text{post}} = 4 + 28 = 32 \implies \mathbf{\text{Beta}(3, 32)}$$
   - Under $\text{Beta}(3, 32)$:
     $$\mu_{\text{post}} = \frac{3}{35} = \mathbf{0.0857} \quad (8.57\%)$$
     $$\theta_{0.90} = \text{Beta}^{-1}(0.90; 3, 32) = \mathbf{0.1490} \quad (14.90\%)$$
     $$\theta_{0.95} = \text{Beta}^{-1}(0.95; 3, 32) = \mathbf{0.1738} \quad (17.38\%)$$
   - The Step 4D.4 author copied the numerical output ($\theta_{0.90} \approx 0.149$) from the actual runtime execution but wrote the algebraic label $\text{Beta}(3, 29)$ based on an unverified flat prior assumption.

2. **Why the Proposed `abs(qualification_mean - threshold) <= 0.015` Condition Fails:**
   - Under the benchmark threshold $\tau = 0.15$:
     $$\text{qualification\_mean} = \mu_{\text{post}} = 0.085714$$
     $$|\mu_{\text{post}} - \tau| = |0.085714 - 0.150000| = \mathbf{0.064286} \quad (6.43\%)$$
   - The condition tests:
     $$0.064286 \le 0.015 \implies \mathbf{FALSE}$$
   - **Conclusion:** The proposed rule **DOES NOT intercept this false pause**.
   - **Root Cause of the Proposal Error:** The author confused the **posterior mean** ($\mu_{\text{post}}$) with the **decision variable** (the credible-interval upper bound $\theta_{\text{high}}$).
     Rule 6 triggers when $\theta_{\text{high}} < \tau$. When an ad is on the verge of being falsely paused, $\theta_{\text{high}} \approx \tau$. Because $\theta_{\text{high}}$ is an upper quantile (90th or 95th percentile) of a distribution with positive variance, it is *always significantly greater than the posterior mean*:
     $$\theta_{\text{high}} - \mu_{\text{post}} = 0.1490 - 0.0857 = 0.0633 \quad (6.33\%)$$
     Whenever Rule 6 fires near the boundary, the posterior mean is necessarily $5\%-8\%$ below $\tau$. An abstention check on $|\mu_{\text{post}} - \tau| \le 0.015$ only triggers if $\mu_{\text{post}} \in [0.135, 0.165]$, in which case $\theta_{\text{high}} > 0.20$, where Rule 6 is not even remotely close to triggering!
   - In our empirical evaluation over 450 ads, the literal proposal intercepted exactly **0 out of 450 ads (0.00%)**, producing results 100% identical to the unmodified baseline.

---

## 2. Rigorous Separation of the Five Statistical Quantities

| Quantity | Mathematical Symbol | Exact Formal Definition | Where it Exists / Used | Example Value from Ad `385a21d5` |
|---|---|---|---|---|
| **True Qualification Rate** | $q_{\text{true}}$ | The unobservable, latent parameter of the Bernoulli lead-qualification process: $P(\text{Qualified} \mid \text{Contact}) = q_{\text{true}}$. | **Hidden Ground Truth.** Only exists in simulation / historical holdout. Used strictly for post-hoc policy scoring. Never accessible to estimator or engine. | $q_{\text{true}} = 0.1641$ (16.41%, ground-truth "good" ad) |
| **Observed Qualification Rate** | $\hat{q}_{\text{obs}}$ | The empirical sample proportion: $\hat{q}_{\text{obs}} = \frac{k}{N}$, where $k$ is mature qualified leads, and $N$ is mature contacts. | **Empirical Sample.** High variance at small $N$. Unregularized by prior knowledge. | $\hat{q}_{\text{obs}} = \frac{2}{30} = 0.0667$ (6.67%) |
| **Posterior Mean** | $\mu_{\text{post}}$ | The Bayesian expected value under conjugate update: $\mathbb{E}[q \mid k, N] = \frac{\alpha_0 + k}{\alpha_0 + \beta_0 + N}$. | **Bayesian Point Estimate.** Regularized shrinkage of $\hat{q}_{\text{obs}}$ toward prior mean $\frac{\alpha_0}{\alpha_0 + \beta_0} = 0.20$. Available in `estimate.qualification_mean`. | $\mu_{\text{post}} = \frac{1 + 2}{1 + 4 + 30} = \frac{3}{35} = 0.0857$ (8.57%) |
| **Credible-Interval Upper Bound** | $\theta_{\text{high}}$ | The upper quantile $1 - \frac{1 - \text{ci\_level}}{2}$ of the posterior $\text{Beta}(\alpha_{\text{post}}, \beta_{\text{post}})$ distribution: $\theta_{\text{high}} = F^{-1}(p; \alpha, \beta)$. | **Decision Metric for Rule 6.** Represents the optimistic bound: "We are $X\%$ confident the true rate is at most $\theta_{\text{high}}$." Available in `estimate.qualification_ci_high`. | $\theta_{0.90} = 0.1490$ (80% CI)<br>$\theta_{0.95} = 0.1738$ (90% CI) |
| **Policy Pause Threshold** | $\tau_{\text{pause}}$ | The business hurdle below which an ad is declared conclusively unviable. Configured in `DecisionPolicy.low_qualification_upper_bound`. | **Policy Standard.** Constant business parameter. Rule 6 triggers when $\theta_{\text{high}} < \tau_{\text{pause}}$. | Production: $\tau = 0.10$ (10.0%)<br>Benchmark: $\tau = 0.15$ (15.0%) |

---

## 3. Production Policy Baseline vs Counterfactual Candidates Evaluation

Evaluated across 190 deterministic, paired simulation runs (450 total ads; 50 continuous runs [seeds 22000–22049], 50 bimodal runs [seeds 24000–24049], and 90 preset runs [seeds 26001–26010]):

### 3.1 Empirical Comparison Table

| Policy Configuration | Intercepted Decisions | Benchmark Hurdle ($\tau = 0.15$)<br>False Pause Rate [95% Wilson CI] | Benchmark Hurdle ($\tau = 0.15$)<br>Missed Poor Rate [95% Wilson CI] | Spend on Poor Ads ($\tau = 0.15$) | Mean Pause Day [Counts: D3, D7, D14, D21] | Total Spend | Total Qualified Leads | Portfolio CPQL |
|---|---|---|---|---|---|---|---|---|
| **1. Unmodified Production Baseline**<br>*(ci=0.90, N=20, thresh=0.10)* | **0** | **0.38%** (1/262)<br>[0.07%, 2.13%] | **65.43%** (123/188)<br>[58.38%, 71.85%] | ₹790,500.00 | **18.67**<br>[0, 0, 22, 44] | ₹2,158,000.00 | 5,226 | **₹412.94** |
| **2. Literal Proposal Abstention**<br>*(abs(mean − thresh) $\le$ 0.015, thresh=0.10)* | **0** | **0.38%** (1/262)<br>[0.07%, 2.13%] | **65.43%** (123/188)<br>[58.38%, 71.85%] | ₹790,500.00 | **18.67**<br>[0, 0, 22, 44] | ₹2,158,000.00 | 5,226 | **₹412.94** |
| **3. Corrected Boundary Candidate**<br>*(abs(ci_high − thresh) $\le$ 0.015, N < 40, thresh=0.10)* | **16** | **0.38%** (1/262)<br>[0.07%, 2.13%] | **71.28%** (134/188)<br>[64.43%, 77.27%] | ₹816,500.00 | **19.22**<br>[0, 0, 14, 41] | ₹2,184,000.00 | 5,242 | **₹416.63** |
| **4. Production Policy on 0.15 Hurdle**<br>*(ci=0.90, N=20, thresh=0.15)* | **0** | **1.53%** (4/262)<br>[0.60%, 3.86%] | **38.83%** (73/188)<br>[32.15%, 45.95%] | ₹705,250.00 | **18.71**<br>[0, 0, 39, 80] | ₹2,067,750.00 | 5,171 | **₹399.87** |
| **5. Corrected Boundary on 0.15 Hurdle**<br>*(abs(ci_high − 0.15) $\le$ 0.015, N < 40, thresh=0.15)* | **12** | **1.53%** (4/262)<br>[0.60%, 3.86%] | **42.55%** (80/188)<br>[35.70%, 49.70%] | ₹719,000.00 | **18.81**<br>[0, 0, 35, 77] | ₹2,081,500.00 | 5,179 | **₹401.91** |
| **6. Step 4D Experimental Baseline**<br>*(ci=0.80, N=12, thresh=0.15)* | **0** | **5.73%** (15/262)<br>[3.50%, 9.23%] | **25.00%** (47/188)<br>[19.35%, 31.65%] | ₹590,750.00 | **15.75**<br>[0, 0, 117, 39] | ₹1,927,250.00 | 5,012 | **₹384.53** |

*Note: When evaluated under production hurdle $\tau = 0.10$ ($q_{\text{true}} < 0.10$ is poor, $N_{\text{poor}}=160$, $N_{\text{good}}=290$):*
- *Config 1 & 2: False Pause Rate = 1.03% (3/290 [0.35%, 3.00%]); Missed Poor Rate = 60.62% (97/160 [52.89%, 67.86%]); Spend on Poor = ₹653,000.00.*
- *Config 3: False Pause Rate = 1.03% (3/290 [0.35%, 3.00%]); Missed Poor Rate = 67.50% (108/160 [59.91%, 74.27%]); Spend on Poor = ₹679,000.00.*

---

## 4. Analysis of Trade-offs

1. **Failure of Boundary Abstention Under Conservative Production Defaults:**
   - Under `ci_level = 0.90` and `thresh = 0.10`, the baseline false-pause rate is already negligible (**0.38%** under benchmark hurdle, **1.03%** under 0.10 hurdle).
   - The corrected boundary rule intercepted 16 pause recommendations, but **none of them were false pauses**. All 16 were genuinely poor campaigns ($q_{\text{true}} \in [0.03, 0.08]$) that happened to have $\theta_{0.95} \in [0.085, 0.100]$.
   - Consequently, the candidate boundary rule caused **11 additional missed poor ads** (+5.85% missed-poor rate), allowed poor campaigns to run for additional checkpoints, increased spend on poor ads by **+₹26,000.00**, and **worsened portfolio CPQL** from ₹412.94 to ₹416.63.

2. **The Same Failure Replicates Under Hurdle 0.15:**
   - Under `ci_level = 0.90` and `thresh = 0.15`, the candidate boundary rule intercepted 12 decisions.
   - The false pause rate remained completely unchanged at **1.53% (4/262)** because the 4 false pauses had $\theta_{0.95} < 0.135$ (outside the $\pm 1.5\%$ window).
   - Missed poor ads increased from 73 to 80 (+3.72%), spend on poor ads increased by **+₹13,750.00**, and portfolio CPQL degraded from ₹399.87 to ₹401.91.

---

## 5. Critical Simulator Limitations & Business Misalignment

> [!WARNING]
> **Severe Simulator / Runtime Configuration Divergence:**
> 1. **Threshold Disconnect:** The benchmark simulator's synthetic scenarios (e.g. `continuous_intent`) classify an ad as `"bad"` if $q_{\text{true}} < 0.15$. However, the production runtime policy defaults to `low_qualification_upper_bound = 0.10` ($10\%$).
> 2. **Artificial "Missed Poor Ad" Inflation:** When the production policy runs against the benchmark simulator, any ad with $q_{\text{true}} \in [0.10, 0.15)$ is considered acceptable by the production policy, yet scored as a "missed poor ad" by the benchmark suite. This accounts for why the production policy exhibits a staggering **65.43% missed poor ad rate** against benchmark labels.
> 3. **Sample Size vs 90% Credible Interval:** In production, requiring $\theta_{0.95} < 0.10$ requires $N \ge 25$ with 0 qualified leads ($k=0$), or $N \ge 42$ with 1 qualified lead ($k=1$). At typical traffic rates (5 leads/day, 60% reachability), an ad only generates ~30–35 mature contacts by Day 21. If a genuinely poor ad ($q_{\text{true}} = 0.04$) gets even a single lucky qualification ($k=1$), it cannot be paused before Day 28 under production defaults.
> 4. **Methodological Conclusion:** Tuning boundary heuristics on a simulator that uses a 15% hurdle to guide decisions for a production engine configured with a 10% threshold creates invalid causal conclusions.

---

## 6. Recommendations & Remaining Evidence Needed

1. **Reject the Boundary-Abstention Proposal:**
   - The literal proposal `abs(qualification_mean - threshold) <= 0.015` is mathematically defective and intercepts 0 decisions.
   - The corrected proposal `abs(qualification_ci_high - threshold) <= 0.015` produces zero reduction in false pauses under production settings while increasing missed poor ads, increasing wasted ad spend, and worsening portfolio CPQL.

2. **Align Simulator Hurdle with Authoritative Business Economics Before Policy Tuning:**
   - Either production `low_qualification_upper_bound` should be realigned to the true business viability threshold (e.g. 0.15), or the benchmark simulator's continuous scenario must be parameterized to match the production 0.10 threshold.
   - Cross-evaluating mismatched thresholds creates phantom defects and misleading trade-off conclusions.

3. **Required Evidence Before Any Future Production Change:**
   - An agreed business definition of the minimum viable qualification rate ($10\%$ vs $15\%$).
   - A dual-criterion evaluation measuring both *decision accuracy* (FP, Missed Bad) and *economic regret* (actual spend wasted on poor ads vs revenue lost from prematurely paused good ads).
   - Validation across an independent holdout dataset to prevent post-hoc over-fitting to specific synthetic seeds.
