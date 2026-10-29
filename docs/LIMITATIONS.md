# QualLoop — Limitations

**Version:** 0.1  
**Date:** 2026-10-14  
**Important:** Read this before drawing conclusions from QualLoop outputs.

---

## 1. This is a Prototype on Simulated Data

QualLoop operates entirely on synthetically generated data. It has not been tested on
real advertising campaigns. All results shown in the dashboard reflect simulated scenarios
designed to demonstrate the system's reasoning — not its real-world performance.

Do not present QualLoop benchmark results as evidence of improvements in actual ad spend
efficiency. They are evidence that the methodology handles specific simulated edge cases
better than a naive baseline.

---

## 2. The Simulator is Simplified

Real advertising generates far more complex data than QualLoop's simulator produces:

- Real leads may come from multiple touchpoints (multi-touch attribution ignored in v1)
- Real contactability depends on time of day, geography, device type, and lead quality signals
  not captured here
- Real qualification processes vary by sales team, product, and market conditions
- Real CRM data contains noise, duplicate entries, and attribution errors
- Simulated creative fatigue uses a simple decay function; real fatigue is harder to model

---

## 3. Statistical Model Limitations

### Beta-Binomial assumptions

The Beta-Binomial model assumes each lead is an independent Bernoulli trial. In reality:
- Leads from the same campaign are correlated (they share targeting)
- Contactability is not independent of lead quality (LTV-optimized targeting affects both)
- Qualification outcomes may cluster by lead source in ways the model does not capture

### Prior sensitivity

The Beta(1,4) qualification prior encodes an expectation of ~20% qualification rate. If the
actual business has a very high qualification rate (e.g., 60%) or a very low one (e.g., 2%),
this prior will bias estimates in the first few dozen observations. For v1, this is documented
and accepted.

### CPQL instability

When the estimated qualification count is near zero, CPQL estimates become unstable and can
produce very wide or undefined intervals. This is handled explicitly in the UI, but the underlying
instability is a genuine property of ratio estimators.

### No hierarchical model in v1

Ads within the same campaign share a targeting strategy and market context. A hierarchical model
would allow them to borrow statistical strength from each other. In v1, each ad is modeled
independently. This means an ad with 5 leads gets little benefit from the 500 leads in a sibling ad.

### Maturity window is a fixed constant

The contact maturity window (3 days default) is a single configurable value. In real campaigns,
response time distributions are highly skewed — most leads respond within hours; a long tail
extends to weeks. A fixed window creates some bias at the tail.

---

## 4. Decision Engine Limitations

### Thresholds are not calibrated to real data

The decision thresholds (e.g., reachability CI upper bound < 25%, qualification CI upper bound
< 10%) were chosen to be reasonable for a prototype. They have not been calibrated on real
advertising data. They may be too aggressive or too conservative for specific businesses.

### No learning from historical decisions

In v1, the decision engine does not learn from the outcomes of its past recommendations. If a
recommended investigation was resolved without action, that resolution is not fed back into future
decisions for that ad.

### No budget constraints in the simulation

The simulator does not model real budget constraints (daily budget caps, bid adjustments, etc.)
that would affect how spend is actually distributed in real campaigns.

---

## 5. Meta Conversions API

The feedback module builds and validates CAPI event payloads but does not transmit them. In
dry-run mode, nothing is sent to Meta. The payload structure is based on Graph API (version unverified)
documentation reviewed at the time of writing. Meta's API specifications change over time and
would need to be re-verified before any live integration.

Live integration would require:
- A valid Meta Business Manager account
- A verified pixel (or dataset)
- Correct access token with `ads_management` and `business_management` permissions
- Compliance with Meta's Terms of Service and Data Policy
- A deduplication strategy using both pixel and server-side events

---

## 6. What QualLoop Does Not Claim

- **No Gross Lead Superiority Over Tuned Heuristics:** When naive Baseline C is properly tuned (30 mature contacts, 0.10 hurdle), its holdout qualified lead output (4,840.88) is statistically indistinguishable from QualLoop's (4,805.88; paired difference $\Delta = -0.35$ leads/run, 95% bootstrap CI $[-1.44, 0.57]$). QualLoop provides credible intervals, uncertainty quantification, and audit compliance—not magical lead volume advantages.
- **Continuous Boundary Fragility:** On continuous buying intent distributions, QualLoop's false-pause rate jumps from 1.4% on discrete bimodal clusters to 23.5% (8/34). Point and interval thresholds alike exhibit high sampling noise near the hurdle boundary.
- **Diminishing Returns Sensitivity:** Under linear returns ($Spend^{1.0}$), QualLoop delivers 4,805.88 leads; under concave diminishing returns ($Spend^{0.7}$), audience fatigue reduces realized volume to 3,739.50 leads.
- **Intent vs. Economic Divergence:** An ad with high conversion intent ($q=20\%$) can still be commercially disastrous if top-of-funnel CPL is excessive (`high_cpql` realizes CPQL $\approx ₹2,976 \gg ₹500$). Qualification gating alone cannot substitute for unit economic cost ceilings.
- It does not claim to be causally correct. Differences between ads may be due to targeting differences, not creative quality.
- It does not claim to automatically improve ROAS. It recommends; humans decide.
- It does not claim that its benchmark results predict live real-world performance improvements.
- It does not claim that its statistical model is the best possible model for this problem. Survival models, multilevel models, and time-series approaches may be more appropriate for specific use cases.

---

## 7. Future Work

To address these limitations in future versions:

1. Calibrate priors from a real business's historical qualification rate distribution
2. Add a hierarchical model for within-campaign shrinkage
3. Add a survival model for qualification time distributions
4. Add multi-touch attribution for cross-ad lead crediting
5. Add feedback learning: resolution outcomes from prior recommendations improve future ones
6. Validate maturity windows against real response time data
7. Add real advertising platform integration (Meta, Google) with proper auth and compliance
