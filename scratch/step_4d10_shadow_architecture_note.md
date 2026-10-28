# Step 4D.10 — Isolated Shadow-Mode Foundation Architecture Note

**Document Status:** Version 1.0.0 (OFFLINE REPLAY & TEST FIXTURES ONLY — NOT DEPLOYED TO PRODUCTION)  
**Author:** Evaluation Engineering & Platform Security Team  
**Date:** October 28, 2026  
**Companion Artifacts:**  
- Versioned Event Contracts: [`backend/shadow/contracts.py`](file:///d:/Developer/qualloop/backend/shadow/contracts.py)
- Isolated Shadow Sink: [`backend/shadow/sink.py`](file:///d:/Developer/qualloop/backend/shadow/sink.py)
- Offline Shadow Runner: [`backend/shadow/runner.py`](file:///d:/Developer/qualloop/backend/shadow/runner.py)
- Automated Isolation Test Suite: [`backend/tests/test_step_4d10_shadow_isolation.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d10_shadow_isolation.py)
- Serialized Event Examples: [`scratch/step_4d10_example_shadow_events.json`](file:///d:/Developer/qualloop/scratch/step_4d10_example_shadow_events.json)

---

## 1. Executive Summary & Design Scope

Step 4D.10 establishes an isolated, non-actioning shadow-evaluation and telemetry foundation for QualLoop. The system runs an economic decision evaluator in parallel with the active production decision path, logging rich economic telemetry while maintaining a strict zero-mutation boundary.

### Key Guarantees:
1. **Zero External Action:** Shadow evaluations are strictly informational. The runner has no client bindings or credentials for Meta Marketing API or Google Ads API.
2. **Unaltered Production Behavior:** The existing heuristic decision engine (`DecisionPolicy` + `evaluate_campaign`) remains the sole authority for all production actions. The shadow runner returns production decisions completely unaltered.
3. **Dedicated Telemetry Path:** Shadow events (`SHADOW_ECONOMIC_DECISION_LOGGED` v1.0.0) are written to a segregated sink (`ShadowEventSink`), completely separated from the audit trail (`backend.audit.trail`). Shadow events cannot be mistaken for enacted decisions by compliance audits or client dashboards.
4. **No Uncalibrated Confidence Claims:** Pydantic schema validation forbids phrases such as "95.8% confidence" or "statistically confirmed". All model intervals and probabilities carry an explicit `calibration_status="EXPLORATORY_NOT_CALIBRATED"` tag.
5. **Principled Abstention & Error Isolation:** When business assumptions (e.g. lead valuation $V_{\text{QL}}$) are missing, the evaluator explicitly abstains (`ABSTAIN_MISSING_ASSUMPTIONS`) without guessing universal constants. Runtime failures are recorded as `ERROR` and never silently defaulted to `CONTINUE` or `PAUSE`.

---

## 2. Trust Boundaries & Architecture Diagram

```mermaid
graph TD
    subgraph Active Production Pipeline [AUTHORITATIVE PRODUCTION BOUNDARY]
        PlatformTelemetry[Telemetry Ingestion] --> SnapshotGen[Compute Campaign Estimates]
        SnapshotGen --> ProdEngine[Production Heuristic Engine: Rule 6]
        ProdEngine --> ProdAuditTrail[Production Audit Trail: backend.audit.trail]
        ProdEngine --> ProdActionOut[Enacted Decision Stream: CONTINUE / PAUSE]
    end

    subgraph Shadow Isolation Sandbox [NON-ACTIONING SHADOW SANDBOX]
        SnapshotGen -. Read-Only Snapshot .-> ShadowRunner[Isolated Shadow Runner: execute_shadow_evaluation]
        BusinessConfig[Client Business Assumptions: V_QL, C_ops] -. Optional Inputs .-> ShadowRunner
        
        ShadowRunner --> EconEvaluator[Economic Model: MC Posterior Sampling]
        EconEvaluator --> SafetyValidation[Pydantic Contract Validator v1.0.0]
        SafetyValidation --> DedicatedSink[Isolated Shadow Sink: backend.shadow.sink]
        
        ShadowRunner -. Forbidden: No Outbound Bindings .x MetaGoogleAPI[Meta / Google Ads API]
    end

    classDef prod fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef shadow fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef blocked fill:#ffebee,stroke:#b71c1c,stroke-width:2px,stroke-dasharray: 5 5;
    
    class PlatformTelemetry,SnapshotGen,ProdEngine,ProdAuditTrail,ProdActionOut prod;
    class ShadowRunner,BusinessConfig,EconEvaluator,SafetyValidation,DedicatedSink shadow;
    class MetaGoogleAPI blocked;
```

### Trust Boundary Rules:
- **Rule 1 (Data Flow):** Production telemetry flows unidirectionally into the shadow runner. No data flows from the shadow runner into the production engine, production audit store, or external network.
- **Rule 2 (Fail-Safe Execution):** Any exception inside the shadow sandbox (e.g., corrupt telemetry, mathematical domain error, missing input) is caught and isolated as a `ShadowAction.ERROR` event. The production decision continues uninterrupted.
- **Rule 3 (Idempotency):** The shadow sink indexes events by `(advertisement_id, snapshot_computed_at, evaluator_version)`. Reprocessing the same snapshot produces zero duplicate events.

---

## 3. Versioned Event Schema Contract (`v1.0.0`)

The contract [`ShadowEconomicDecisionLoggedEvent`](file:///d:/Developer/qualloop/backend/shadow/contracts.py#L112) is defined using Pydantic v2 with strict type validation:

### 3.1 Schema Definition
- **`event_id`** (`UUID`): Unique event identifier.
- **`timestamp`** (`datetime`, UTC): UTC time of shadow logging.
- **`schema_version`** (`Literal["1.0.0"]`): Strict schema versioning.
- **`evaluator_version`** (`str`): Git or semantic version of the evaluator (e.g., `economic_evaluator_v1_prototype`).
- **`policy_version`** (`str`): Identifier of the active production baseline policy.
- **`campaign_id`**, **`advertisement_id`**, **`creative_id`** (`str`): Tenant-scoped campaign entities (free of lead-level PII).
- **`decision_time_snapshot`** ([`DecisionTimeSnapshot`](file:///d:/Developer/qualloop/backend/shadow/contracts.py#L52)): Sanitized input metrics available at decision time (`cumulative_spend`, `current_day`, `n_leads`, `n_contacts`, `n_mature_contacts`, `k_qualified`, `reachability_mean`, `qualification_mean`, `provenance`).
- **`business_assumptions`** ([`ShadowBusinessAssumptions`](file:///d:/Developer/qualloop/backend/shadow/contracts.py#L26)): Explicit parameters (`lead_value`, `cost_per_lead`, `cost_per_call`, `decision_horizon_days`, `status`, `provenance`, `config_version`).
- **`shadow_decision`** ([`ShadowEconomicDecision`](file:///d:/Developer/qualloop/backend/shadow/contracts.py#L86)):
  - `action`: `CONTINUE`, `PAUSE`, `ABSTAIN_INSUFFICIENT_EVIDENCE`, `ABSTAIN_MISSING_ASSUMPTIONS`, or `ERROR`.
  - `reason`: Auditable reason string using neutral model-derived exploratory language.
  - `expected_incremental_spend`, `expected_incremental_ql`, `expected_incremental_profit`, `profit_interval_low`, `profit_interval_high`, `expected_cpql`, `breakeven_cpql`.
  - `exploratory_probability_profitable`: Continuous value $[0.0, 1.0]$.
  - `calibration_status`: Strictly `EXPLORATORY_NOT_CALIBRATED`.
- **`production_action_taken`** (`str`): Production action enacted concurrently (e.g., `CONTINUE`, `PAUSE`).
- **`production_reason`** (`str`): Production rule reasoning string.
- **`is_shadow_only`** (`Literal[True]`): Invariant boolean `True`.
- **`external_action_taken`** (`Literal[False]`): Invariant boolean `False`.

---

## 4. Uncertainty Language Guardrails

To eliminate misleading pseudo-confidence claims (such as converting $P(\Pi > 0) = 0.042$ into "95.8% confidence it loses money"), the Pydantic schema enforces the following validation checks:

1. **Forbidden Term Detection:** Reject any event whose reason string contains phrases like:
   - `"confidence that it loses money"`
   - `"statistically confirmed"`
   - `"confident it loses"`
2. **Confidence Percentage Clamp:** Reject any percentage claim formatted as `X% confidence` unless explicitly accompanied by `model-derived interval` or `credible interval configuration`.
3. **Mandatory Disclaimer:** All probability figures must be accompanied by explicit text: `(uncalibrated estimate)` or `(uncalibrated parameter estimate)`.

---

## 5. Failure Modes & Behavioral Matrix

| Scenario / Condition | Shadow Action | Reason Text Pattern | Production Action | External Mutation |
|---|---|---|---|---|
| **Profitable Campaign ($\mathbb{E}[\Pi] > 0$)** | `CONTINUE` | `"Exploratory model projection indicates non-negative incremental contribution profit..."` | Unaltered (Heuristic) | None (`False`) |
| **Capital Destroying Campaign ($\mathbb{E}[\Pi] < 0, P \le 10\%$)** | `PAUSE` | `"Exploratory model projection indicates negative incremental contribution profit..."` | Unaltered (Heuristic) | None (`False`) |
| **Early Checkpoint ($M_{\text{mat}} < 60\%$ or $N_{\text{mat}} < 20$)** | `ABSTAIN_INSUFFICIENT_EVIDENCE` | `"Contact maturity fraction ... below required ... Continuing autonomous observation."` | Unaltered (Heuristic) | None (`False`) |
| **Missing Lead Valuation ($V_{\text{QL}} = \text{None}$)** | `ABSTAIN_MISSING_ASSUMPTIONS` | `"Shadow economic evaluator abstained: required commercial business input 'lead_value' is missing..."` | Unaltered (Heuristic) | None (`False`) |
| **Corrupt Telemetry / Type Error** | `ERROR` | `"Shadow economic evaluator snapshot parsing failure: ValueError: ..."` | Unaltered (Heuristic) | None (`False`) |
| **Evaluator Runtime Crash** | `ERROR` | `"Shadow economic evaluator runtime failure: <ExceptionType>: ..."` | Unaltered (Heuristic) | None (`False`) |

---

## 6. Verification and Test Coverage

Automated testing in [`backend/tests/test_step_4d10_shadow_isolation.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d10_shadow_isolation.py) provides 7 regression tests:
1. `test_shadow_cannot_invoke_ad_mutation_or_external_clients`: AST inspection guarantees zero external HTTP mutation verbs or ad SDK imports.
2. `test_production_decision_unaltered`: Proves production actions and reasons pass through 100% unaltered.
3. `test_misleading_confidence_language_rejected`: Proves schema rejects "95.8% confidence" derived from $p=0.042$.
4. `test_idempotent_event_sink`: Proves duplicate snapshot processing logs zero duplicate events.
5. `test_missing_business_assumptions_abstains`: Proves missing $V_{\text{QL}}$ triggers explicit abstention without fallback constants.
6. `test_evaluator_error_records_explicit_error`: Proves runtime crashes emit `ERROR` events without defaulting to `CONTINUE` or `PAUSE`.
7. `test_production_audit_trail_completely_isolated`: Proves zero shadow events leak into `backend.audit.trail`.

**Full Backend Test Suite:** **202 passed, 0 failed in 43.22s.**

---

## 7. Work Required Before Live Shadow Deployment

*Offline replay and test fixtures are fully functional. The following items are strictly required before enabling shadow evaluation on live client accounts:*

1. **Client Valuation Ingestion Pipeline:** Build database schema and API endpoints for clients to configure and verify $V_{\text{QL}}$, $c_{\text{lead}}$, and $c_{\text{call}}$ with explicit audit provenance.
2. **Persistent Shadow Event Storage:** Implement an asynchronous, write-ahead PostgreSQL/ClickHouse shadow event sink decoupled from the primary application transaction pool.
3. **Poisson Arrival Calibration:** Upgrade the Monte Carlo model in `scratch/economic_evaluator.py` to draw Poisson arrivals and Binomial realizations before evaluating calibration in production.
4. **Worker Isolation Deployment:** Package the shadow runner as an asynchronous background Celery/Sidecar worker listening to a read-only message queue, with zero outbound egress to ad platform endpoints.
5. **Operational Dashboarding:** Develop an internal telemetry dashboard displaying shadow vs production agreement rates, latency distribution, and abstention frequencies.
