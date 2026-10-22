# QualLoop — Specification Deviations & Gap Analysis

**Date:** 2026-10-22  
**Purpose:** Comprehensive audit of current codebase against core requirements and specifications (`docs/PRODUCT_REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/STATISTICAL_MODEL.md`, `docs/DECISION_POLICY.md`, `docs/BENCHMARK_METHODOLOGY.md`).

---

## 1. Statistical Estimator & Priors

| Specification Item | Current Implementation | Status | Deviation Details |
|---|---|---|---|
| **Hierarchical Empirical-Bayes Shrinkage** | Fixed conjugate prior in `estimator/estimator.py:32-36` ($\text{Beta}(1,1)$ for reach, $\text{Beta}(1,4)$ for qualification). | **DEVIATION** | No empirical Bayes pooling or Method-of-Moments fitting across campaign/portfolio ads. Priors are static constants. |
| **Random Number Generator Seed** | `compute_estimates` in `estimator/estimator.py:96` uses `rng = np.random.default_rng()` if `rng` is None. | **DEVIATION** | Non-deterministic Monte Carlo CPQL estimates across repeated calls on identical data when `rng` is omitted. Must derive RNG from `(run_seed, ad_id)`. |
| **Maturity Window Gating** | Enforced in `estimator/maturity.py:110-151`. | **ALIGNED** | Pending leads (inside 3-day contact window) and pending contacts (inside 7-day qualification window) are excluded from respective denominators. |
| **Separation of Reach & Intent** | `reach_est` and `qual_est` computed independently in `estimator/estimator.py:109-124`. | **ALIGNED** | Contactability $r$ and qualification intent $q$ are estimated separately. Unreached leads never enter qualification denominator. |
| **CPQL Monte Carlo Propagation** | `estimator/cpql.py:51-147` draws 10,000 samples and evaluates joint distribution. | **ALIGNED** | Correctly captures non-linear ratio uncertainty and flags numerical instability when zero-EQL draws exceed threshold (0.20). |

---

## 2. Decision Engine & Record Schema

| Specification Item | Current Implementation | Status | Deviation Details |
|---|---|---|---|
| **`tier` field** | Uses `confidence_level` (`"high"`, `"medium"`, `"low"`) in `domain/models.py:172`. | **DEVIATION** | Missing explicit `tier` enum (`gated`, `within_guardrails`, `autonomous`). |
| **`auto_applied` field** | Uses `requires_human_approval` (bool) and `approval_status` (`ApprovalStatus`) in `domain/models.py:173-174`. | **DEVIATION** | Missing explicit `auto_applied` boolean field on `Decision` model. |
| **Action Tier Classification** | Generic `requires_approval` boolean in `decision_engine/engine.py:281`. | **DEVIATION** | Budget raises/launches must strictly be `tier=gated, auto_applied=false`. Pausing/reallocating must be `within_guardrails` with configurable caps. |
| **Relative Cross-Ad Comparison Rule** | Only evaluates absolute thresholds (`cpql_ci_low > high_cpql_lower_bound`). | **DEVIATION** | Missing relative rule: If one ad's CPQL credible interval sits entirely above another ad's interval in the same campaign, emit guardrailed spend shift recommendation. |
| **Reason Formulation** | Semi-templated strings in `decision_engine/engine.py`. | **PARTIAL** | Plain-language explanations must directly incorporate exact calculated bounds, delta numbers, and context without generic boilerplates. |

---

## 3. Decision Audit & Storage

| Specification Item | Current Implementation | Status | Deviation Details |
|---|---|---|---|
| **PostgreSQL Persistence** | In-memory store in `api/store.py` and `audit/trail.py`. `persistence/alembic` is empty scaffolding. | **DEVIATION** | All runs and decisions vanish on process restart. |
| **Audit Completeness** | `Decision` records inputs, posterior stats, and thresholds in `supporting_metrics`. | **ALIGNED** | Records are immutable and append-only in memory. |

---

## 4. Meta Conversions API (CAPI) Module

| Specification Item | Current Implementation | Status | Deviation Details |
|---|---|---|---|
| **Dry-Run Enforcement** | `feedback/builder.py:153` sets status to `DRY_RUN`. No live HTTP transmission. | **ALIGNED** | Payloads are created and validated without transmitting. |
| **Event Ingestion Timing Window** | `feedback/builder.py:114` rejects events older than 7 days (`age_days > 7.0`). | **DEVIATION** | Needs reconciliation against official Meta documentation regarding the 7-day server event ingestion window vs. 28-day conversion attribution window. |
| **Placement of `lead_id`** | Placed in `custom_data.lead_id` in `feedback/builder.py:131`. | **PENDING VERIFICATION** | Must verify against official Meta Conversion Leads CRM integration documentation whether `lead_id` belongs in `user_data` or `custom_data`. |
| **PII Hashing** | SHA-256 applied to synthetic lead ID proxy. | **ALIGNED** | Correctly enforces normalized SHA-256 hex digest. |
| **Idempotency Keying** | 32-character SHA-256 key derived from outcome and lead IDs. | **ALIGNED** | Prevents duplicate ingestion. |

---

## 5. Benchmark Module & Presets

| Specification Item | Current Implementation | Status | Deviation Details |
|---|---|---|---|
| **Paired Evaluation Across Seeds** | 200 pre-committed seeds in `benchmark/seeds.json` across 9 scenarios. | **ALIGNED** | Evaluates naive baseline vs QualLoop against hidden simulator ground truth. |
| **Reported Metrics** | FPPR, FNDR, IER, QLUS, and cases where QualLoop performed worse. | **ALIGNED** | Reports honest tradeoffs and error rates. |
| **`days_to_correct_decision` Metric** | Not tracked or reported in `benchmark/runner.py`. | **DEVIATION** | Days elapsed before reaching correct decision is not calculated. |
| **Correlation-Variant Scenarios** | Simulator draws reachability and intent independently per ad. | **DEVIATION** | No joint reach-intent correlated scenario preset. |
