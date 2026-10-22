# QualLoop — Decision Policy

**Version:** 0.1  
**Date:** 2026-10-14

---

## 1. Policy Overview

The decision engine converts estimate snapshots into recommendations using deterministic rules.
Policy parameters are configurable and versioned. Changing any threshold constitutes a new
policy version. Every recommendation records the policy version used.

---

## 2. Policy Parameters (v0.1 defaults)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_mature_leads_for_reachability` | 30 | Minimum mature leads before reachability evidence is trusted |
| `min_mature_contacts_for_qualification` | 20 | Minimum mature contacts before qualification evidence is trusted |
| `min_maturity_fraction` | 0.60 | Minimum fraction of leads that must be mature |
| `low_reachability_upper_bound` | 0.25 | CI upper bound below this → investigate reachability |
| `low_qualification_upper_bound` | 0.10 | Qualification CI upper bound below this → consider pause |
| `high_cpql_lower_bound` | 500.0 | CPQL CI lower bound above this → consider reallocation |
| `target_cpql` | 75.0 | CPQL CI upper bound below this with mature evidence → raise budget (gated) |
| `cooldown_hours` | 48 | Minimum simulated hours between actions on same ad |
| `floor_spend_fraction` | 0.20 | Ad cannot be paused if it represents < 20% of campaign |
| `budget_guardrail_min_spend` | 100.0 | Minimum spend per ad before reallocation is suggested |
| `spend_shift_cap_fraction` | 0.25 | Maximum fraction of budget shifted between ads in one action |
| `guardrail_action_spend_cap` | 500.0 | Actions on ads with spend under this cap are auto-applied within guardrails |
| `abnormal_change_threshold` | 0.30 | Relative change in qualification rate triggering anomaly flag |

---

## 3. Decision Rules (in priority order)

Rules are evaluated in order. The first matching rule produces the recommendation.

### Rule 1: Insufficient Maturity

**Condition:** `maturity_fraction_contact < min_maturity_fraction`  
**Action:** `flag_insufficient_evidence`  
**Reason:** "Less than {min_maturity_fraction*100:.0f}% of leads have reached the contact maturity
window. Current estimates reflect early data only."  
**Human approval required:** No  
**Notes:** This rule fires even if sample size is large. Maturity takes priority over count.

### Rule 2: Insufficient Sample Size

**Condition:** `n_mature_leads < min_mature_leads_for_reachability`  
**Action:** `collect_more_data`  
**Reason:** "Only {n_mature_leads} mature leads observed. Minimum required is
{min_mature_leads_for_reachability} for reliable reachability estimates."  
**Human approval required:** No

### Rule 3: Insufficient Qualification Sample

**Condition:** `evidence_sufficient = False` for qualification (n_mature_contacts < threshold)  
**Action:** `collect_more_data`  
**Reason:** "Only {n_mature_contacts} contacts with resolved qualification. Minimum is
{min_mature_contacts_for_qualification}."  
**Human approval required:** No

### Rule 4: Abnormal Performance Change

**Condition:** Recent (last 7 days) qualification rate differs from prior period by >
`abnormal_change_threshold` relative  
**Action:** `flag_abnormal_change`  
**Reason:** "Qualification rate has changed by {change:.0%} relative to the prior 14-day period.
This may indicate creative fatigue, targeting drift, or a data quality issue."  
**Human approval required:** Yes  
**Notes:** Does not itself recommend pausing. Triggers investigation.

### Rule 5: Low Reachability

**Condition:** `reachability_ci_high < low_reachability_upper_bound` AND sample is sufficient  
**Action:** `investigate_low_reachability`  
**Reason:** "The 90% credible interval for reachability [{ci_low:.1%}, {ci_high:.1%}] is entirely
below {low_reachability_upper_bound:.0%}. This ad generates leads that are difficult to contact.
Buying intent cannot be assessed until reachability improves."  
**Human approval required:** No  
**Notes:** Does NOT recommend pausing. Low reachability is a reachability problem, not a quality
problem. Qualification rate on the few reached leads may be excellent.

### Rule 6: Strong Evidence of Low Qualification

**Condition:** `qualification_ci_high < low_qualification_upper_bound` AND
             `n_mature_contacts >= min_mature_contacts_for_qualification` AND
             `reachability_ci_low >= low_reachability_upper_bound` (reachability is not the problem)  
**Action:** `consider_pause`  
**Reason:** "With {n_mature_contacts} resolved contacts, the 90% credible interval for
qualification rate is [{ci_low:.1%}, {ci_high:.1%}] — entirely below {threshold:.0%}.
There is strong evidence this ad generates leads with low buying intent."  
**Human approval required:** Yes  
**Notes:** Requires human approval before any actual pause. QualLoop does not pause ads automatically.

### Rule 7: High Cost Per Qualified Lead

**Condition:** `cpql_ci_low > high_cpql_lower_bound` AND EQL evidence is sufficient  
**Action:** `consider_reallocate`  
**Reason:** "The estimated cost per qualified lead has a 90% CI lower bound of
${cpql_ci_low:.0f}, exceeding the threshold of ${threshold:.0f}. Consider reallocating spend
to higher-performing ads."  
**Human approval required:** Yes

### Rule 8: Budget Guardrail

**Condition:** Any of rules 6 or 7 would fire, BUT `ad_spend < budget_guardrail_min_spend`  
**Action:** `continue_monitoring` (override rules 6, 7)  
**Reason:** "Spend is too low to make a confident reallocation recommendation. Increase budget
for a statistically meaningful test."  
**Human approval required:** No

### Rule 9: High-Performing Ad Budget Expansion

**Condition:** Mature evidence on reachability and qualification, `not cpql_unstable`, and `cpql_ci_high < target_cpql`  
**Action:** `raise_budget`  
**Tier:** `gated` (`auto_applied=False`, `requires_human_approval=True`)  
**Reason:** "Mature evidence confirmed ({n_mature_leads} mature leads, {n_mature_contacts} contacts, {k_qualified} qualified). Credible interval upper bound for CPQL (${cpql_ci_high:.2f}) is strictly below target CPQL (${target_cpql:.2f}) with mean CPQL ${cpql_mean:.2f}. Recommend raising budget (gated tier: human approval required)."  
**Human approval required:** Yes (always gated)

### Rule 10: Continue Monitoring (Default)

**Condition:** None of the above rules fired  
**Action:** `continue_monitoring`  
**Reason:** "Sample is mature and sufficient. No strong signal detected. Continue collecting data."  
**Human approval required:** No

---

## 4. Interpretation Guide

| Action | Tier | Auto-Applied | Meaning for User |
|--------|------|--------------|-----------------|
| `collect_more_data` | autonomous | Yes | Wait — sample size insufficient for reliable inference |
| `flag_insufficient_evidence` | autonomous | Yes | Not enough time has passed; pending leads still maturing |
| `continue_monitoring` | autonomous | Yes | Performance acceptable or within bounds; ongoing surveillance |
| `investigate_low_reachability` | autonomous | Yes | Check phone numbers, lead forms, CRM webhook cadence |
| `flag_abnormal_change` | gated | No | Sudden performance shift detected; human investigation needed |
| `pause_ad` | within_guardrails | Yes | Poor buying intent confirmed under guardrail spend cap; auto-paused |
| `consider_pause` | within_guardrails | No | Poor buying intent confirmed over guardrail spend cap; review recommendation |
| `shift_spend` | within_guardrails | Yes/No | Statistically separated CPQL between ads; shift budget within cap |
| `reallocate_budget` | within_guardrails | Yes | CPQL exceeded threshold under guardrail spend cap; auto-reallocated |
| `consider_reallocate` | within_guardrails | No | CPQL exceeded threshold over guardrail spend cap; review recommendation |
| `raise_budget` | gated | No | Mature ad with CPQL upper bound below target; human approval required to scale |

---

## 5. What the System Will Never Do Automatically

- Pause an advertisement
- Change advertising spend
- Create or delete campaigns
- Contact leads on behalf of the business
- Transmit data to Meta without dry-run mode explicitly disabled

---

## 6. Policy Versioning

Policy is stored as a versioned configuration object. Any change to a threshold value increments
the version. Audit records store the full policy object, not just its version number, so
historical recommendations can always be re-evaluated in context.

Current version: `v0.1.0`
