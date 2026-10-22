# QualLoop — Statistical Model

**Version:** 0.1  
**Date:** 2026-10-14  
**Status:** Specification — implementation in `backend/estimator/`

---

## 1. Problem Framing

We observe a stream of leads for each ad. Each lead proceeds through a funnel:

```
Lead Created
    └─► Contact Attempted?
            ├─ NO (maturity window not yet elapsed) → PENDING
            ├─ NO (window elapsed, never attempted) → UNCONTACTABLE
            └─ YES
                └─► Contact Made?
                        ├─ NO → UNREACHABLE
                        └─ YES → CONTACTED
                                    └─► Qualification Resolved?
                                            ├─ NO → PENDING_QUALIFICATION
                                            ├─ YES → QUALIFIED
                                            └─ NO → DISQUALIFIED
```

We must estimate:
1. How likely is a lead to be contacted (reachability)?
2. How likely is a contacted lead to qualify (intent)?
3. How many qualified leads can we expect per ad?
4. How much does each qualified lead cost?
5. How confident are we in each estimate?

---

## 2. Maturity Windows

### Contact Maturity Window

A lead is considered "mature for reachability analysis" if the configurable
`contact_maturity_days` have elapsed since lead creation. Default: 3 days.

- Leads inside this window: **PENDING** — excluded from reachability denominator
- Leads past this window, contacted: included in reachability numerator and denominator
- Leads past this window, never contacted: included in denominator only (counted as unreachable)

### Qualification Maturity Window

A contacted lead is mature for qualification analysis if `qualification_maturity_days`
have elapsed since the contact was made. Default: 7 days.

- Contacts inside this window: **PENDING_QUALIFICATION** — excluded from intent denominator
- Contacts past this window, qualified: included in intent numerator and denominator
- Contacts past this window, disqualified: included in denominator only

**Critical rule:** A lead that has not been contacted cannot contribute to qualification estimates,
even if it is past the qualification maturity window. Unreachable leads are not disqualifications.

---

## 3. Beta-Binomial Model for Binary Rates

Both reachability and qualification are modeled as independent Bernoulli processes. We use the
Beta-Binomial conjugate model because:

1. The likelihood is Binomial: P(k successes | n trials, p) = Binomial(n, p)
2. The prior is Beta: p ~ Beta(α, β)
3. The posterior is analytically tractable: p | data ~ Beta(α + k, β + n − k)

### 3.1 Reachability Rate

**Observation space:**
- n_r = number of leads past contact maturity window
- k_r = number of those leads who were successfully contacted

**Prior:** Beta(α_r, β_r) where α_r = 1, β_r = 1 (uniform — no prior preference)

**Posterior:** Beta(1 + k_r, 1 + n_r − k_r)

**Point estimate (posterior mean):** p̂_r = (1 + k_r) / (2 + n_r)

**90% credible interval:** [scipy.stats.beta.ppf(0.05, 1 + k_r, 1 + n_r − k_r),
                              scipy.stats.beta.ppf(0.95, 1 + k_r, 1 + n_r − k_r)]

Note: The posterior mean is the natural Bayesian point estimate. It regularizes toward 0.5 when n_r
is small (uniform prior contribution is relatively large), which is the desired behavior.

### 3.2 Qualification Rate (Intent)

**Observation space:**
- n_q = number of contacts past qualification maturity window with resolved outcomes
- k_q = number of those contacts who were qualified

**Prior:** Beta(α_q, β_q) where α_q = 1, β_q = 4 (encodes weak expectation ~20% qualify)

This prior is configurable. Setting α_q = β_q = 1 gives a uniform prior. The Beta(1,4) prior
encodes that we expect roughly 1 in 5 contacted leads to qualify. This shrinks small samples
toward 20% rather than toward 50%, which is more realistic for sales contexts. The choice of
prior should be revisited when real data is available.

**Posterior:** Beta(1 + k_q, 4 + n_q − k_q)

**Point estimate (posterior mean):** p̂_q = (1 + k_q) / (5 + n_q)

**90% credible interval:** [scipy.stats.beta.ppf(0.05, 1 + k_q, 4 + n_q − k_q),
                              scipy.stats.beta.ppf(0.95, 1 + k_q, 4 + n_q − k_q)]

---

## 4. Estimated Qualified Leads

### 4.1 Point Estimate

For a set of N total leads in a campaign observation window:

- Expected mature leads for contact = N × maturity_fraction_r
  where maturity_fraction_r = n_r / N
- Expected qualified leads (point):
  EQL = N × maturity_fraction_r × p̂_r × p̂_q

However, note that this chained estimate has compounding uncertainty.

### 4.2 Uncertainty via Monte Carlo

To propagate uncertainty through the chain, we draw S = 10,000 samples from each posterior:

```
p_r_samples ~ Beta(1 + k_r, 1 + n_r − k_r)    # S samples
p_q_samples ~ Beta(1 + k_q, 4 + n_q − k_q)    # S samples
eql_samples = N × maturity_fraction_r × p_r_samples × p_q_samples
```

**Point estimate of EQL:** mean(eql_samples)  
**90% CI of EQL:** [percentile(5, eql_samples), percentile(95, eql_samples)]

This approach correctly captures the full joint uncertainty including the zero cases.

---

## 5. Estimated Cost Per Qualified Lead (CPQL)

### 5.1 Definition

CPQL = total_spend / estimated_qualified_leads

### 5.2 Instability Problem

When estimated_qualified_leads → 0, CPQL → ∞. This is a genuine instability that must not be
hidden. We handle it explicitly:

- If the 5th percentile of EQL is ≤ 0.5, CPQL is reported as "unstable — insufficient qualified
  leads"
- If 90% CI of EQL spans zero to a large value, CPQL uncertainty is "very high"

### 5.3 CPQL Interval

```
cpql_samples = total_spend / eql_samples  (where eql_samples > 0)
```

Zero-EQL samples are excluded from the CPQL distribution but their count is reported as
"fraction of outcomes with no qualified leads."

**Point estimate:** spend / mean(eql_samples)  
**90% CI:** [percentile(5, valid_cpql_samples), percentile(95, valid_cpql_samples)]

---

## 6. Sample Maturity

**Maturity fraction (reachability):** n_r / N  
This measures what fraction of leads have had enough time for contact attempts to resolve.

**Maturity fraction (qualification):** n_q / n_contacts  
This measures what fraction of contacts have had enough time for qualification to resolve.

**Evidence sufficiency:**
- Reachability evidence is "sufficient" if n_r ≥ 30
- Qualification evidence is "sufficient" if n_q ≥ 20
- Below these thresholds, recommendations are conservative by policy

These thresholds are configurable in `DecisionPolicy`.

---

## 7. Hierarchical Extension (Deferred to v1.1)

When multiple ads share a campaign, their qualification rates may be correlated. A hierarchical
Beta-Binomial model would place a hyperprior on the Beta parameters, allowing ads with few leads
to borrow strength from the campaign.

In v1, we use independent ad-level models with informative priors serving as a lightweight proxy
for this shrinkage. This is honest and computationally simple.

---

## 8. Assumptions and Their Limitations

| Assumption | Implication | Known Failure Mode |
|------------|-------------|-------------------|
| Contact and qualification are independent | p_r × p_q is valid | Some ad types self-select for contactability in ways that correlate with intent |
| Beta-Binomial is correctly specified | Posterior is exact | Multi-call contact attempts create partial observations not captured by binary outcome |
| Maturity window is a fixed constant | Clean denominators | High variance in lead response time means some leads mature early, some late |
| Prior Beta(1,4) for qualification | Shrinks toward 20% | Wrong if business has very high or very low qualification rates — should be calibrated |
| No confounding between leads | Each lead is independent | In reality, ad targeting creates correlated subpopulations |
| Spend is observed without noise | CPQL formula is exact | Real ad spend reporting has latency and attribution noise |

---

## 9. Treatment of Edge Cases

| Case | Treatment |
|------|-----------|
| n_r = 0 (no mature leads) | Return prior distribution; flag as "no data" |
| k_r = 0 (no contacts) | Posterior Beta(1, 1+n_r); CPQL flagged as unstable |
| n_q = 0 (no resolved contacts) | Return qualification prior; flag as "no data" |
| k_q = 0 (no qualified) | Posterior Beta(1, 4+n_q); CPQL is very high |
| k_r = n_r (all contacted) | Posterior Beta(1+n_r, 1); CI is tight near 1.0 |
| k_q = n_q (all qualified) | Posterior Beta(1+n_q, 4); CI pulled toward 1.0 with prior |
| spend = 0 | CPQL = 0 (or undefined if EQL > 0 — report as "no spend recorded") |
| Leads with future creation timestamps | Reject with validation error |
| Negative lead counts | Reject with validation error |

---

## 10. Metric Definitions

| Metric | Symbol | Formula | Denominator |
|--------|--------|---------|-------------|
| Reachability rate | p̂_r | (1 + k_r) / (2 + n_r) | Mature leads |
| Qualification rate | p̂_q | (1 + k_q) / (5 + n_q) | Mature resolved contacts |
| Estimated qualified leads | EQL | Monte Carlo mean | All leads × maturity × rates |
| CPQL (point) | CPQL | spend / EQL | Per qualified lead |
| Maturity (contact) | M_r | n_r / N | All leads |
| Maturity (qualification) | M_q | n_q / n_contacts | All contacts |

---

## 11. Relationship to Baseline (Naive) Model

The baseline model (for benchmarking) uses:

- Reachability = k_r / n_r (raw proportion, no Bayesian smoothing)
- Qualification = k_q / n_q (raw proportion, no Bayesian smoothing)
- Treats 0/0 as 0 (silent failure)
- Uses all leads as denominator regardless of maturity
- Makes no distinction between pending and disqualified leads
- Applies fixed threshold: if observed qualification rate < 10%, recommend pause

This baseline has known problems documented in `docs/BENCHMARK_METHODOLOGY.md`.
