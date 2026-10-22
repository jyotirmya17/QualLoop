# QualLoop — Specification Deviations & Gap Analysis

**Date:** 2026-10-22  
**Purpose:** Comprehensive audit of current codebase against core requirements and specifications (`docs/PRODUCT_REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/STATISTICAL_MODEL.md`, `docs/DECISION_POLICY.md`, `docs/BENCHMARK_METHODOLOGY.md`).

---

## 1. Statistical Estimator & Priors

| Specification Item | Initial Implementation | Initial Status | Status After Fixes | Details & Resolution |
|---|---|---|---|---|
| **Hierarchical Empirical-Bayes Shrinkage** | Fixed conjugate prior in `estimator/estimator.py` ($\text{Beta}(1,1)$, $\text{Beta}(1,4)$). | **DEVIATION** | **RESOLVED** | Implemented Method of Moments prior fitting across campaign ads in `estimator/shrinkage.py` with $\kappa \in [4.0, 50.0]$ bounds and fallback. Wired into `compute_campaign_estimates`. |
| **Random Number Generator Seed** | Unseeded default RNG in Monte Carlo sampling. | **DEVIATION** | **RESOLVED** | Derived deterministic isolated RNGs from `(seed, ad_id)` via SHA-256 in `derive_rng`. Verified byte-identical benchmark outputs. |
| **Maturity Window Gating** | Enforced in `estimator/maturity.py`. | **ALIGNED** | **ALIGNED** | Pending leads (inside 3-day window) and pending contacts (inside 7-day window) are excluded from respective denominators. |
| **Separation of Reach & Intent** | `reach_est` and `qual_est` computed independently. | **ALIGNED** | **ALIGNED** | Contactability $r$ and qualification intent $q$ estimated separately. Unreached leads never enter qualification denominator. |
| **CPQL Monte Carlo Propagation** | 10,000 samples drawn and joint ratio evaluated. | **ALIGNED** | **ALIGNED** | Correctly captures non-linear ratio uncertainty and flags numerical instability when zero-EQL draws exceed 0.20. |

---

## 2. Decision Engine & Record Schema

| Specification Item | Initial Implementation | Initial Status | Status After Fixes | Details & Resolution |
|---|---|---|---|---|
| **`tier` field** | Uses `confidence_level` (`"high"`, `"medium"`, `"low"`). | **DEVIATION** | **RESOLVED** | Added `DecisionTier` enum (`gated`, `within_guardrails`, `autonomous`) and assigned to every `Decision`. |
| **`auto_applied` field** | Relied solely on `requires_human_approval`. | **DEVIATION** | **RESOLVED** | Added explicit `auto_applied: bool` field to `Decision` model and evaluation logic. |
| **Action Tier Classification** | Generic `requires_approval` boolean. | **DEVIATION** | **RESOLVED** | Budget raises/launches are hardcoded to `tier="gated"`, `auto_applied=False`. Pauses and spend shifts are `within_guardrails` up to spend cap ($2,000). |
| **Relative Cross-Ad Comparison Rule** | Only evaluated absolute CPQL thresholds. | **DEVIATION** | **RESOLVED** | Rule 7 evaluates credible interval separation between ads in a campaign and emits guardrailed `DecisionAction.SHIFT_SPEND`. |
| **Reason Formulation** | Semi-templated generic strings. | **PARTIAL** | **RESOLVED** | Reasons incorporate exact observed counts, credible intervals, delta percentages, and threshold numbers without boilerplate. |

---

## 3. Decision Audit & Storage

| Specification Item | Initial Implementation | Initial Status | Status After Fixes | Details & Resolution |
|---|---|---|---|---|
| **PostgreSQL Persistence** | In-memory store in `api/store.py` and `audit/trail.py`. Alembic scaffolding empty. | **DEVIATION** | **REMAINS DEVIATION** | In-memory persistence only; runs and decision records do not survive process termination. |
| **Audit Completeness** | Inputs, posterior stats, and thresholds recorded in `supporting_metrics`. | **ALIGNED** | **ALIGNED** | Records are immutable and append-only in memory with full evidence structure. |

---

## 4. Meta Conversions API (CAPI) Module

| Specification Item | Initial Implementation | Initial Status | Status After Fixes | Details & Resolution |
|---|---|---|---|---|
| **Dry-Run Enforcement** | `feedback/builder.py` sets status to `DRY_RUN`. No HTTP calls. | **ALIGNED** | **ALIGNED** | Payloads are generated and validated without outbound transmission. |
| **`action_source` Parameter** | Was set to `"crm"`. | **DEVIATION** | **RESOLVED** | Corrected to `"system_generated"` per official Meta Conversion Leads CRM integration documentation. |
| **`custom_data` Source Tracking** | Only included `lead_id` and `ad_id`. | **DEVIATION** | **RESOLVED** | Now includes `lead_event_source` (CRM name) and `event_source="crm"` as required for Conversion Leads registration. |
| **Placement of `lead_id`** | Placed inside `custom_data`. | **DEVIATION** | **RESOLVED** | Placed in `user_data["lead_id"]` as raw unhashed string (15–17 digits) per Meta specification. |
| **Full Lifecycle History** | Emitted only final qualification snapshot. | **DEVIATION** | **RESOLVED** | Implemented `build_lead_history_events` emitting raw-lead creation event plus distinct status transitions. |
| **Event Ingestion Timing Window** | Enforced 7-day cutoff without lead creation order check. | **DEVIATION** | **RESOLVED** | Enforces `upload_time - event_time <= 7 days`, `event_time >= lead_created_at`, and `event_time - lead_created_at <= 28 days`. |
| **Batch Size Cap & Fit Checks** | No batch limit validation or account fit checks. | **DEVIATION** | **RESOLVED** | Added `validate_batch` (1,000-event cap) and `check_business_fit` (200 leads/mo, 1%–40% stage conversion rate). |
| **PII Hashing** | SHA-256 applied to emails and phone numbers. | **ALIGNED** | **ALIGNED** | Correctly enforces normalized SHA-256 hex digest. |
| **Idempotency Keying** | 32-character SHA-256 key from outcome and lead IDs. | **ALIGNED** | **ALIGNED** | Deterministic deduplication keying. |

---

## 5. Benchmark Module & Presets

| Specification Item | Initial Implementation | Initial Status | Status After Fixes | Details & Resolution |
|---|---|---|---|---|
| **Paired Evaluation Across Seeds** | 200 pre-committed seeds in `benchmark/seeds.json` across 9 scenarios. | **ALIGNED** | **ALIGNED** | A total of **200 simulations** (evaluating 350 ads) are executed across 9 scenario presets (25 each for 6 scenarios, 20 each for 2 scenarios, 10 for 1 scenario), paired seed-by-seed against baseline. |
| **Reported Metrics** | FPPR, FNDR, IER, QLUS, and worse cases. | **ALIGNED** | **ALIGNED** | Accurately reports tradeoff metrics with Wilson score confidence intervals. |
| **`days_to_correct_decision` Metric** | Not tracked in `benchmark/runner.py`. | **DEVIATION** | **REMAINS DEVIATION** | Rolling time-to-decision tracking is not implemented. |
| **Correlation-Variant Scenarios** | Reachability and intent drawn independently. | **DEVIATION** | **REMAINS DEVIATION** | Joint reach-intent bivariate correlation distribution is not simulated. |
