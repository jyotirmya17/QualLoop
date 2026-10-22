# QualLoop — Architecture

**Version:** 0.1  
**Date:** 2026-10-14

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           QualLoop System                           │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  Simulator   │───►│  Persistence │◄───│   FastAPI Backend    │  │
│  │  (Python)    │    │  (Postgres)  │    │   (Python 3.11+)     │  │
│  └──────┬───────┘    └──────────────┘    └──────────────────────┘  │
│         │                    ▲                       ▲              │
│         │ hidden ground      │                       │              │
│         │ truth (benchmark   │                       │ REST API     │
│         │ only)              │                       │              │
│         ▼                    │              ┌─────────────────────┐ │
│  ┌─────────────┐             │              │  Next.js Dashboard  │ │
│  │  Benchmark  │─────────────┘              │  (TypeScript)       │ │
│  │  Module     │                            └─────────────────────┘ │
│  └─────────────┘                                                     │
│                                                                      │
│  Backend Internal Modules:                                           │
│  ┌───────────┐  ┌───────────┐  ┌─────────────┐  ┌───────────────┐ │
│  │ estimator │  │ decision  │  │   audit     │  │   feedback    │ │
│  │           │  │ _engine   │  │   trail     │  │   (CAPI)      │ │
│  └───────────┘  └───────────┘  └─────────────┘  └───────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Responsibilities

### `simulator/`
Generates synthetic advertising and lead data from configured scenarios and seeds.
- Exposes: `SimulationRun`, `ScenarioConfig`, `run_simulation(config) -> SimulationResult`
- Contains: hidden ground truth (never exported to production modules)
- Key constraint: must be deterministic given the same seed

### `domain/`
Core business objects shared across modules.
- Contains: Pydantic models and SQLAlchemy ORM models for all entities
- No business logic; pure data containers and validation
- Key entities: Campaign, AdSet, Advertisement, Lead, CallAttempt, QualificationOutcome

### `estimator/`
Computes statistical estimates from observed lead data.
- Input: list of domain objects (Lead, CallAttempt, QualificationOutcome), policy config
- Output: `EstimateSnapshot` containing rates, credible intervals, maturity metrics
- Implements: Beta-Binomial model, Monte Carlo CPQL propagation
- Zero dependencies on FastAPI, SQLAlchemy, or the simulator

### `decision_engine/`
Converts estimates into recommendations.
- Input: `EstimateSnapshot`, `DecisionPolicy`, prior recommendations (for cooldown)
- Output: `Decision` with action, reason, evidence, and approval status
- No database access; no API layer
- Deterministic: same inputs → same output

### `audit/`
Persists and queries decision records.
- Stores: inputs, estimate snapshots, policy version, recommendation, timestamp
- Provides: queryable audit trail API
- Append-only by design (records are never deleted or mutated after creation)

### `feedback/`
Builds Meta Conversions API event payloads from qualified leads.
- Input: validated QualificationOutcome records
- Output: `FeedbackEvent` Pydantic model (validated payload structure)
- Dry-run only by default: logs payload without transmitting
- Separate from any actual HTTP client code

### `api/`
FastAPI application exposing REST endpoints.
- Delegates to estimator, decision_engine, audit, feedback
- No statistical logic
- Validates inputs with Pydantic
- Returns structured JSON responses

### `persistence/`
SQLAlchemy models and Alembic migrations.
- Defines database schema
- Provides session management utilities
- Contains no business logic

### `benchmark/`
Runs comparative experiments between baseline and QualLoop policies.
- Only module with access to simulator ground truth
- Runs N independent simulation runs with different seeds
- Outputs machine-readable JSON results and human-readable Markdown report

### `tests/`
pytest test suite organized by module.

---

## Data Flow

### Simulation → Estimation → Decision

```
ScenarioConfig (seed, scenario_name, time_horizon)
    │
    ▼
simulator.run_simulation()
    │ produces: Campaign, AdSet, Ad, Lead, CallAttempt, QualificationOutcome
    ▼
persistence.save_simulation_run()
    │ persists to PostgreSQL
    ▼
estimator.compute_estimates(ad_id, policy)
    │ reads: Lead, CallAttempt, QualificationOutcome
    │ applies: maturity windows, Beta-Binomial model, Monte Carlo
    │ produces: EstimateSnapshot
    ▼
decision_engine.evaluate(estimate_snapshot, policy, prior_decisions)
    │ applies: thresholds, cooldowns, guardrails
    │ produces: Decision
    ▼
audit.record(decision)
    │ persists: all evidence + recommendation
    ▼
api.GET /ads/{id}/recommendations → dashboard
```

### Feedback Flow

```
QualificationOutcome (qualified=True, resolved=True)
    │
    ▼
feedback.build_event(outcome) → FeedbackEvent (validated payload)
    │
    ▼
feedback.process_dry_run(event) → logs payload, returns processing record
    │ (future: feedback.transmit_to_meta(event) would replace dry run)
    ▼
audit.record_feedback_event(record)
```

---

## Database Schema (Conceptual)

```
simulation_runs
  id, scenario_name, seed, started_at, completed_at, config_json

campaigns
  id, simulation_run_id, name, total_spend, created_at

ad_sets
  id, campaign_id, name, spend

advertisements
  id, ad_set_id, creative_id, spend, impressions, clicks

leads
  id, advertisement_id, created_at, status, source

call_attempts
  id, lead_id, attempted_at, outcome (answered|no_answer|voicemail|disconnected)

qualification_outcomes
  id, lead_id, resolved_at, result (qualified|disqualified), notes

estimate_snapshots
  id, advertisement_id, computed_at, estimator_version, n_leads, n_mature_leads,
  n_contacts, n_mature_contacts, k_qualified, reachability_mean, reachability_ci_low,
  reachability_ci_high, qualification_mean, qualification_ci_low, qualification_ci_high,
  eql_mean, eql_ci_low, eql_ci_high, cpql_mean, cpql_ci_low, cpql_ci_high,
  maturity_fraction_contact, maturity_fraction_qualification, evidence_sufficient

decisions
  id, advertisement_id, estimate_snapshot_id, policy_version, action, reason,
  supporting_metrics_json, confidence_level, requires_human_approval, approval_status,
  created_at

audit_events
  id, decision_id, event_type, data_json, created_at

feedback_events
  id, qualification_outcome_id, event_name, event_time, payload_json,
  validation_status, processing_status, idempotency_key, created_at

benchmark_runs
  id, started_at, completed_at, n_simulations, scenario_distribution_json,
  qualloop_config_json, baseline_config_json, results_json
```

---

## Key Architectural Boundaries

| Boundary | Why It Matters |
|----------|----------------|
| Simulator ground truth never reaches estimator | Prevents evaluating what we cannot know in production |
| Estimator has no DB dependency | Can be unit-tested with pure Python objects |
| Decision rules in decision_engine only | Changes to policy do not require API changes |
| Audit records are append-only | Preserves historical decision trail for accountability |
| Feedback module builds but never sends | Safe to run in development without credentials |
| Frontend computes nothing | Statistical correctness lives in the backend |

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend runtime | Python | 3.11+ |
| API framework | FastAPI | 0.115+ |
| Schema validation | Pydantic | v2 |
| ORM | SQLAlchemy | 2.x |
| Migrations | Alembic | latest |
| Database | PostgreSQL | 15+ |
| Numerics | NumPy, SciPy | latest |
| Testing | pytest | latest |
| Linting | Ruff | latest |
| Frontend | Next.js + TypeScript | 14+ |
| Charts | Recharts | latest |
| Container | Docker + Docker Compose | latest |

---

## Directory Structure

```
qualloop/
├── backend/
│   ├── simulator/
│   │   ├── __init__.py
│   │   ├── config.py          # ScenarioConfig, SimulatorConfig
│   │   ├── engine.py          # run_simulation()
│   │   ├── scenarios.py       # Named preset scenarios
│   │   └── ground_truth.py    # Hidden truth (benchmark access only)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py          # Pydantic domain models
│   │   └── enums.py           # Status enums
│   ├── estimator/
│   │   ├── __init__.py
│   │   ├── maturity.py        # Maturity window logic
│   │   ├── beta_binomial.py   # Core statistical model
│   │   ├── cpql.py            # CPQL Monte Carlo estimation
│   │   └── estimator.py       # compute_estimates() entry point
│   ├── decision_engine/
│   │   ├── __init__.py
│   │   ├── policy.py          # DecisionPolicy dataclass
│   │   └── engine.py          # evaluate() deterministic rules
│   ├── audit/
│   │   ├── __init__.py
│   │   └── trail.py           # record(), query()
│   ├── feedback/
│   │   ├── __init__.py
│   │   ├── builder.py         # build_event() → FeedbackEvent
│   │   └── validator.py       # CAPI payload validation
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI app
│   │   ├── routers/
│   │   │   ├── simulations.py
│   │   │   ├── campaigns.py
│   │   │   ├── ads.py
│   │   │   ├── decisions.py
│   │   │   ├── audit.py
│   │   │   └── feedback.py
│   │   └── schemas/
│   │       └── responses.py
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── database.py        # Engine, session
│   │   ├── models.py          # SQLAlchemy ORM models
│   │   └── alembic/
│   ├── benchmark/
│   │   ├── __init__.py
│   │   ├── baseline.py        # Naive policy implementation
│   │   └── runner.py          # run_benchmark() → BenchmarkResult
│   └── tests/
│       ├── test_simulator.py
│       ├── test_estimator.py
│       ├── test_decision_engine.py
│       ├── test_feedback.py
│       └── test_api.py
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── tsconfig.json
├── docs/
│   ├── REFERENCE_RESEARCH.md
│   ├── PRODUCT_REQUIREMENTS.md
│   ├── ARCHITECTURE.md
│   ├── STATISTICAL_MODEL.md
│   ├── DECISION_POLICY.md
│   ├── BENCHMARK_METHODOLOGY.md
│   ├── SECURITY.md
│   ├── API.md
│   └── LIMITATIONS.md
├── docker-compose.yml
├── .env.example
└── README.md
```
