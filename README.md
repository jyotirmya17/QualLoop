# QualLoop

**An Uncertainty-Aware Lead Qualification and Advertising Feedback System**

> ⚠ **SIMULATED DATA — NOT CONNECTED TO A LIVE AD ACCOUNT.**  
> QualLoop is an empirical software and applied statistics system demonstrating uncertainty-aware decision making for high-consideration advertising funnels.

---

## 1. Problem Statement

Standard advertising platforms (Meta, Google, TikTok) optimize for top-of-funnel conversion signals: clicks, landing page views, and form submissions. In businesses with sales qualification cycles (B2B SaaS, real estate, healthcare, financial services), these metrics are misleading:

1. **Contactability is not intent**: A lead who does not answer the phone is uncontacted, not disqualified. Counting unreachable leads as low-intent corrupts creative evaluation.
2. **Outcomes are delayed and immature**: Naive analysis windows count pending leads as failures, prematurely penalizing high-intent cohorts with long sales cycles.
3. **Small sample noise creates illusory winners and losers**: Standard dashboards report raw point ratios (e.g. 1 qualified out of 2 leads = "50% qualification rate") without credible intervals.

QualLoop decouples **Reachability (Contactability)** from **Qualification Intent**, enforces **Cohort Maturity Gating**, represents uncertainty via **Bayesian Beta-Binomial inference**, and guards advertising budgets with an **immutable decision audit trail**.

---

## 2. Statistical & Architectural Foundations

### 2.1 The Two-Stage Bayesian Model

$$\text{Observed Leads } \xrightarrow{\text{Contactability}} \text{Reached Contacts } \xrightarrow{\text{Qualification Intent}} \text{Verified Buyers}$$

- **Stage 1: Reachability ($\theta_{\text{reach}}$)**
  - Prior: $\text{Beta}(1, 1)$ (uninformative uniform)
  - Denominator: Only mature leads past the contact maturity window (default: 3 days). Pending leads are excluded.
  - Likelihood: $\text{Binomial}(n_{\text{mature}}, k_{\text{contacted}})$
  - Posterior: $\text{Beta}(1 + k_{\text{contacted}}, 1 + n_{\text{mature}} - k_{\text{contacted}})$

- **Stage 2: Qualification Intent ($\theta_{\text{qual}}$)**
  - Prior: $\text{Beta}(1, 4)$ (informative prior encoding ~20% qualification expectation)
  - Denominator: Mature answered contacts only. **Unreachable leads are never counted as disqualified.**
  - Posterior: $\text{Beta}(1 + k_{\text{qualified}}, 4 + n_{\text{mature\_contacts}} - k_{\text{qualified}})$

- **Economic CPQL Uncertainty (Monte Carlo Propagation)**
  - Draws $S = 2,000$ posterior samples: $\text{EQL}^{(s)} = N_{\text{leads}} \times \theta_{\text{reach}}^{(s)} \times \theta_{\text{qual}}^{(s)}$
  - $\text{CPQL}^{(s)} = \frac{\text{Spend}}{\text{EQL}^{(s)}}$
  - Explicitly flags **instability** when posterior mass concentrates near zero EQL rather than outputting infinite or deceptive ratios.

---

## 3. Architecture & Strict Invariant Boundaries

```
qualloop/
├── backend/
│   ├── simulator/        # Synthetic generator with isolated ground truth
│   ├── domain/           # Core Pydantic & domain models
│   ├── estimator/        # Pure Bayesian math & Monte Carlo CPQL (no DB / API dependencies)
│   ├── decision_engine/  # Deterministic recommendation rules & policy versioning
│   ├── audit/            # Append-only decision audit trail
│   ├── feedback/         # Meta Conversions API (CAPI v21.0) dry-run payload builder
│   ├── benchmark/        # Paired empirical evaluation against ground truth
│   ├── api/              # FastAPI REST endpoints
│   └── tests/            # Full test suite (99 passing tests)
├── frontend/             # React + TypeScript + Vite Dashboard (Dark mode glassmorphism)
└── docs/                 # PRD, Architecture, Statistical Model, Decision Policy, Benchmarks
```

### Key Architectural Boundaries

| Boundary | Enforcement Mechanism |
|---|---|
| **Ground Truth Isolation** | Hidden truth ($p_{\text{reach}}$, $p_{\text{intent}}$) exists only in the simulator and is accessed solely by the `benchmark/` module. Production API views strip all ground truth. |
| **Estimator Independence** | `estimator/` depends only on domain objects and standard numerics (`numpy`, `scipy`). Zero dependency on FastAPI or persistence. |
| **Decision Engine Location** | Recommendation rules reside exclusively in `decision_engine/`, never in routers or frontend components. |
| **Audit Completeness** | Every recommendation is immutably logged with its supporting statistical snapshot, policy version, and rationale. |
| **Feedback Safety** | Meta Conversions API events are validated and cryptographically hashed (SHA-256) in dry-run mode without live network transmission. |

---

## 4. Empirical Benchmark: QualLoop vs. Naive Baseline

The benchmark runner executes a paired comparison across pre-committed random seeds (`backend/benchmark/seeds.json`) across 9 scenario presets:

- **False Positive Pause Rate (FPPR)**: QualLoop reduced premature pausing of good ads from **1.7% to 0.0%** (target: < 10%).
- **Insufficient Evidence Rate (IER)**: QualLoop explicitly identifies cohorts where data is insufficient (**12.0%**), whereas the naive baseline never admits ignorance.
- **Scientific Honesty & Transparency**: In small sample traps, naive policies occasionally pause genuinely poor ads early purely by chance; QualLoop prudently flags `collect_more_data` or `flag_insufficient_evidence`, prioritizing evidence over premature guessing.

---

## 5. Quickstart & Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 1. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .

# Run the complete test suite (99 unit & integration tests)
python -m pytest tests/ -v

# Run the FastAPI server
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install

# Run the Vite development server
npm run dev
# Accessible at http://127.0.0.1:3000
```

---

## 6. Dashboard Features

- **Portfolio Overview**: Live KPI cards for spend, mature lead volume, EQL credible intervals, reachability, qualification, and CPQL stability.
- **Campaign & Creative Table**: Visual credible interval bars for reachability and qualification, maturity badges, and action recommendations.
- **Ad Inspector Modal**: Detailed Bayesian decomposition, Beta distribution parameters, evidence sufficiency checks, and decision justification.
- **Benchmark Lab**: Head-to-head empirical metrics (FPPR, FNDR, IER) and per-scenario breakdowns against hidden ground truth.
- **Decision Audit Trail**: Queryable, append-only ledger displaying the exact rationale and policy inputs for every action.
- **System Health Diagnostics**: Real-time architectural boundary verification and API connectivity monitoring.
