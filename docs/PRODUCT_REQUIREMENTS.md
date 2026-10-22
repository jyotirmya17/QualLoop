# QualLoop — Product Requirements Document

**Version:** 0.1  
**Date:** 2026-10-14  
**Status:** Initial — reflects intended v1 scope only

---

## 1. Problem Statement

Advertising dashboards measure impressions, clicks, form submissions, and cost-per-lead. These
metrics are insufficient for businesses whose value is determined by whether a lead becomes a
qualified buyer — not merely whether they clicked an ad.

Two additional failure modes compound the problem:

1. **Contactability is not guaranteed.** A lead who does not answer the phone is not automatically
   a bad lead. Their qualification intent is simply unobserved.

2. **Outcomes are delayed and incomplete.** A lead created yesterday may not be contacted for
   days. A contacted lead may not complete qualification for weeks. Treating unresolved leads as
   failures produces systematically biased estimates.

QualLoop addresses both problems by separating reachability from intent, respecting outcome
maturity, representing uncertainty explicitly, and making only evidence-backed recommendations.

---

## 2. Users

Primary user for the initial prototype: a software engineer or technical product manager
evaluating QualLoop's methodology. The system must be self-explanatory and reproducible.

Future users (not in scope for v1): marketing operations teams, growth analysts, advertising
account managers.

---

## 3. Core Components

### 3.1 Synthetic Data Simulator

Generates realistic advertising and lead qualification scenarios using configurable random seeds.

**Outputs:**
- Campaigns, ad sets, individual advertisements, creative identifiers
- Advertising spend, impressions, clicks, lead submissions
- Lead source and campaign attribution, creation timestamps
- Call attempts and call outcomes (answered, no answer, voicemail, disconnected)
- Contactability probability (per ad, configurable)
- Buying intent probability (per ad, configurable, hidden ground truth)
- Qualification outcomes (qualified, disqualified, unresolved)
- Delayed outcomes with configurable maturity window
- Creative fatigue progression

**Scenario Presets:**

| Name | Description |
|------|-------------|
| `healthy_campaign` | Balanced performance across ads |
| `good_ad_low_reachability` | High intent but low contactability |
| `bad_ad_high_engagement` | Many clicks/leads, low qualification rate |
| `small_sample_trap` | Few leads with misleadingly high early rates |
| `delayed_conversion_trap` | Most outcomes arrive after naive analysis window |
| `creative_fatigue` | Performance degrades over simulated time |
| `mixed_portfolio` | Heterogeneous ads in one campaign |
| `high_cpql` | Good quality but expensive leads |
| `sudden_deterioration` | Ad performs well then degrades sharply |

**Ground truth isolation:**
- Hidden true reachability and intent probabilities are stored in the simulator's internal state
- These values are never exposed to the estimator, decision engine, or dashboard
- Tests may access ground truth for evaluation only via explicit benchmark interfaces

### 3.2 Statistical Estimator

Estimates per-ad performance metrics from observed data, with explicit uncertainty.

**Estimates produced:**
- Reachability rate with credible interval
- Qualification rate (among contacted leads with resolved outcomes) with credible interval
- Estimated qualified lead count with credible interval
- Estimated cost per qualified lead (CPQL) with uncertainty representation
- Sample maturity fraction (proportion of leads past maturity window)
- Evidence sufficiency flag
- Data freshness timestamp

**Statistical approach:**
- Beta-Binomial conjugate model for binary outcomes
- See `docs/STATISTICAL_MODEL.md` for full specification

**Hard rules:**
- Pending leads are not failures
- Unreachable leads inform reachability estimates but never qualification estimates
- Qualification denominator is only resolved contacts
- Zero-denominator cases produce explicit "insufficient data" results, not NaN or division errors
- Credible intervals must always be computed and reported

### 3.3 Decision Engine

Converts estimator outputs into actionable recommendations with justification.

**Possible actions:**

| Action | Trigger Condition |
|--------|------------------|
| `collect_more_data` | Sample maturity or count below minimum threshold |
| `continue_monitoring` | Evidence present, no strong signal either way |
| `investigate_low_reachability` | Reachability CI upper bound below threshold |
| `refresh_creative` | Qualification rate acceptable, but reachability declining |
| `consider_pause` | Strong evidence of low qualification, sample mature |
| `consider_reallocate` | CPQL credible interval lower bound exceeds portfolio threshold |
| `flag_insufficient_evidence` | Leads exist but maturity < minimum fraction |
| `flag_abnormal_change` | Recent estimate significantly different from prior window |

**Decision constraints:**
- Minimum sample size (default: 30 mature leads)
- Minimum maturity fraction (default: 0.6)
- Cooldown period between actions on same ad (default: 48 hours simulated time)
- Budget guardrail: no reallocation recommendation if it would drop ad below floor spend

**Architectural rule:** Decision rules live only in `decision_engine/`, never in API endpoints.

### 3.4 Decision Audit Trail

Every generated recommendation is stored with:
- Inputs used (ad ID, observation window, estimator version)
- Full estimator outputs and credible intervals
- Policy version and thresholds applied
- Recommended action and its explanation
- Timestamp of recommendation
- Whether human approval is required
- Approval status (default: pending)

### 3.5 Meta Conversions API Feedback Builder

Isolated module that prepares qualified-lead events for Meta's Conversions API.

**Capabilities:**
- Accept validated qualification outcomes from the domain layer
- Build correctly-structured event payloads per Meta CAPI v21.0 specification
- Validate required fields before accepting a payload
- Preserve event timestamps
- Support event deduplication identifiers
- Handle invalid events with structured errors
- Prevent duplicate event processing via idempotency key
- Log all validation and processing outcomes
- Dry-run mode by default (always active in development)

**Not in scope:**
- Real HTTP calls to Meta CAPI (dry-run only in v1)
- OAuth token management

### 3.6 Dashboard

React (Next.js + TypeScript) frontend consuming backend APIs.

**Views:**
1. Portfolio overview — aggregate metrics across all campaigns
2. Campaign and ad-set table with sortable columns
3. Ad-level detail — estimates, intervals, sample size, maturity, recommendations
4. Audit trail — searchable log of all decisions with evidence
5. Simulation controls — choose preset, set seed, run simulation
6. Benchmark results — baseline vs QualLoop comparison charts
7. System health — API status, data freshness, data quality warnings

**Design rules:**
- Every page displays: `⚠ SIMULATED DATA — NOT CONNECTED TO A LIVE AD ACCOUNT`
- Small sample warnings appear when n < 30
- Stale data warnings appear when estimate is > 24 simulated hours old
- Unresolved leads are visually distinct from disqualified leads
- Uncertainty intervals are shown on all estimates, not hidden

---

## 4. Architecture Boundaries

| Boundary | Rule |
|----------|------|
| Ground truth isolation | Simulator exposes ground truth only to `benchmark/` module |
| Estimator independence | Estimator takes only observed data structures, not FastAPI request objects |
| Decision rule location | Rules exist only in `decision_engine/` module |
| Audit completeness | Every recommendation has a corresponding audit record |
| Meta payload isolation | Payload construction is separate from any transmission code |
| Frontend computation | Frontend renders data from API; it does not re-implement statistics |

---

## 5. Non-Functional Requirements

- **Reproducibility:** Same seed → same simulation output, deterministically
- **Testability:** Every module has independent unit tests
- **Correctness over speed:** Statistical correctness takes priority
- **Explainability:** Every recommendation answers: what, estimate, evidence, action, why, unknown
- **Transparency:** Simulated nature always visible; no fake live-data indicators

---

## 6. Out of Scope for v1

- Live advertising account integration
- Real customer data
- LLM-based qualification
- Multi-touch attribution (Shapley, Markov)
- Real-time streaming data
- Redis, Kafka, Kubernetes
- Email or SMS outreach
- A/B testing infrastructure
- Multi-tenant access control

---

## 7. Open Questions

1. Should CPQL uncertainty be expressed as a parametric distribution or a simulation-derived interval?
   → Decision: simulation-based (Monte Carlo from posterior Beta draws) for tractability.

2. What is the right prior for qualification rate? Uniform Beta(1,1) or informative?
   → Decision: Beta(1,1) for reachability, Beta(1,4) for qualification (encoding expectation
   that roughly 1 in 5 contacted leads qualifies — adjustable via config).

3. Should the dashboard support real-time updates?
   → Decision: Polling every 30 seconds is sufficient for v1. WebSockets not needed.
