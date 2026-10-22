# docs/REFERENCE_RESEARCH.md

# QualLoop — Reference Repository Research

**Researcher:** QualLoop Engineering  
**Date:** 2026-10-14  
**Status:** Complete — all 7 repositories inspected

---

## Research Methodology

Each repository was fetched from GitHub via its public URL. Raw README files and
source trees were inspected via the GitHub API. Code files were read directly where
accessible. Where a raw file returned a 404, the branch name was corrected and
retried. Findings below reflect what was actually observed, not assumed.

No code was copied. No findings were fabricated.

---

## Repository 1 — piperun-meta-capi-webhook

**URL:** https://github.com/gabrielbarretodev/piperun-meta-capi-webhook  
**Accessible:** YES (branch is `master`, not `main`)  
**License:** No license file found in repository (unset / all rights reserved)  
**Language:** JavaScript (Node.js)  
**Stars:** 1  
**Last push:** 2026-08-09

### Files Inspected

- `README.md` (Portuguese) — describes a webhook server bridging Piperun CRM events
  to Meta Ads Conversions API v18.0
- `app.js` — Express server receiving webhook POST, extracting contact fields from
  various Piperun payload shapes, SHA-256 hashing PII, then calling Meta CAPI
- `src/services/metaAdsService.js` — Meta CAPI integration service (presence confirmed)
- `src/services/piperunService.js` — Piperun data parsing (presence confirmed)
- `src/utils/logger.js` — structured logging (presence confirmed)
- `test/test-webhook.js` — webhook tests (presence confirmed)
- `Dockerfile`, `.env.example` — Docker configuration

### What Is Actually Present

- Single-file Express server (`app.js`) performing webhook receipt
- Field extraction via multiple lookup paths (direct fields, nested objects, custom_fields array, recursive scan)
- SHA-256 hashing of email and phone before sending to Meta (GDPR/LGPD compliance)
- Support for custom event names: `Reuniao_Agendada`, `No_Show`, `Venda`
- Health check endpoint (`GET /`)
- Environment-variable driven configuration (token, pixel ID)
- Docker deployment target
- No license means code cannot be copied without author permission

### Concepts Worth Learning

- Event naming discipline: business events mapped explicitly to Meta event names
- Multi-path field extraction: real CRM payloads are inconsistent
- Hashing PII before external transmission: SHA-256 on normalized fields
- Health endpoint as operational good practice
- Dry-run mode: NOT present — QualLoop must implement this explicitly

### Parts Irrelevant to QualLoop

- Piperun-specific payload parsing
- Node.js/Express stack (QualLoop uses Python/FastAPI)
- Actual transmission to Meta CAPI

### Ideas We Will Adapt

- Explicit event-name mapping
- Payload validation before any external call
- PII hashing discipline
- Health endpoint pattern

### Ideas We Will Not Implement

- Piperun webhook receiver
- Production Meta CAPI transmission during development

### Uncertainties

- The `metaAdsService.js` source was not fetched. The exact payload structure it
  constructs is unknown. We rely on official Meta Conversions API documentation.

---

## Repository 2 — bayesian-marketing-attribution

**URL:** https://github.com/olivierzach/bayesian-marketing-attribution  
**Accessible:** YES  
**License:** Not explicitly stated; academic course project (Georgia Tech ISYE 6420)  
**Language:** Python (Jupyter notebooks)

### Files Inspected

- `README.md` — describes Bayesian marketing attribution for SaaS company dataset

### What Is Actually Present

- Course project applying Bayesian conjugate pairs to estimate conversion rates by marketing channel
- Beta-Binomial model with credible sets per channel
- Logistic regression on conversion probability given channel
- Motivation addresses small-data problems: channels with weeks of data showing spuriously high rates
- Data: anonymised wins/losses by channel

### Concepts Worth Learning

- **Beta-Binomial conjugate model**: given k successes in n trials, posterior is Beta(a+k, b+n-k)
- **Credible interval derivation**: exact intervals via `scipy.stats.beta.interval`
- **Small-sample shrinkage**: model shrinks estimates toward prior when n is small
- **Hierarchical shrinkage rationale**: campaigns with few leads should borrow portfolio strength

### Parts Irrelevant to QualLoop

- Channel-level attribution (different problem from ad-level lead quality)
- Logistic regression on channel features

### Ideas We Will Adapt

- Beta-Binomial model for reachability rate per ad
- Beta-Binomial model for qualification rate per ad (among contacted leads)
- Prior choice: start with Beta(1, 1) uniform; consider informative priors for shrinkage
- 90% and 95% credible intervals using `scipy.stats.beta.interval`

### Ideas We Will Not Implement

- Multi-channel attribution
- Logistic regression models on channel features

---

## Repository 3 — marketing-mix-allocation (Alloc Signal)

**URL:** https://github.com/UlrikErlingsen/marketing-mix-allocation  
**Accessible:** YES  
**License:** AGPL-3.0-or-later  
**Language:** Python (Streamlit)

### Files Inspected

- `README.md` — 114 lines, extremely detailed

### What Is Actually Present

- Diminishing-return curve-based budget allocation
- Channel-level spend optimization with minima, maxima, fixed commitments
- Marginal return and elasticity reporting
- Panel regression (fixed/random effects, Hausman test)
- Digital economics: CPM, CPC, CTR, CVR, CPA, contribution ROAS, break-even
- Attribution audit with explicit non-causal label
- Sensitivity analysis (low/base/high scenarios)
- Exportable audit trail (XLSX, CSV, JSON)

### Concepts Worth Learning

- **Audit trail philosophy**: "Decision evidence: portable tables and an audit trail
  containing inputs, assumptions, constraints, diagnostics, and warnings."
- **Honest limitation framing**: every disclaimer is a template for LIMITATIONS.md
- **Separation of evidence from recommendation**: mirrors QualLoop's design
- **Sensitivity scenarios**: low/base/high cases for CPQL estimates

### Parts Irrelevant to QualLoop

- Diminishing-return Hill curves (out of scope for v1)
- Streamlit UI (QualLoop uses Next.js)
- Panel econometrics
- Adstock transformations
- AGPL license means no code copying; architecture patterns are general practices

### Ideas We Will Adapt

- Audit trail design: store inputs, assumptions, and reasoning alongside outputs
- Honest limitation labelling
- Sensitivity scenario reporting for CPQL

### Ideas We Will Not Implement

- Marketing mix optimization
- Diminishing-return curves

---

## Repository 4 — OpenCRM (arkitekt-ai)

**URL:** https://github.com/arkitekt-ai/OpenCRM  
**Accessible:** YES  
**License:** MIT  
**Language:** Python (Flask), SQLite

### Files Inspected

- `README.md` — 159 lines

### What Is Actually Present

- Lead status pipeline: `intake -> emailed -> contacted -> qualified -> closed`
- Campaign and source attribution fields
- Webhook ingestion: `POST /api/webhook/leads`
- Duplicate detection by lead ID
- Kanban board and table view
- Docker Compose with two services

### Concepts Worth Learning

- Lead lifecycle state machine matches QualLoop's conceptual flow
- Campaign/ad attribution fields on lead records
- Webhook ingestion endpoint pattern

### Parts Irrelevant to QualLoop

- Email outreach, AI copy generation, Kanban UI
- SQLite (QualLoop uses PostgreSQL)
- Flask (QualLoop uses FastAPI)

### Ideas We Will Adapt

- Lead lifecycle state machine (adapted to QualLoop stages)
- Campaign/ad attribution fields
- Webhook ingestion pattern

### Ideas We Will Not Implement

- Email campaigns or messaging features

---

## Repository 5 — real-estate-lead-automation

**URL:** https://github.com/karl22puday-eng/real-estate-lead-automation  
**Accessible:** YES  
**License:** Not visible  
**Language:** n8n workflow, Supabase, Groq/Gemini LLMs

### Files Inspected

- `README.md` — 97 lines

### What Is Actually Present

- Lead capture from web form or Meta Lead Ads
- RAG-grounded AI qualification using Groq Llama 3.3 70B
- Deterministic 0–100 scoring in code (LLM emits signals; math is separate)
- Idempotent upsert
- Hot-lead routing to Telegram

### Concepts Worth Learning

- Separation of LLM signals from scoring math — mirrors QualLoop's estimator/engine separation
- Idempotent lead processing
- Speed-to-lead framing: highlights business cost of delayed qualification

### Statistical Caveat

The 0–100 scoring formula treats absent information as negative — exactly the
error QualLoop is designed to avoid. QualLoop treats absent information as
uncertainty, not failure.

### Ideas We Will Adapt

- Idempotent simulation run handling
- Observable signal → recommendation pipeline pattern (with statistical layer)

### Ideas We Will Not Implement

- LLM qualification
- 0–100 composite scoring without uncertainty bounds

---

## Repository 6 — Attributor (Crynge)

**URL:** https://github.com/Crynge/Attributor  
**Accessible:** YES  
**License:** MIT  
**Language:** Go  
**CI coverage:** 91%

### Files Inspected

- `README.md` — 79 lines

### What Is Actually Present

- Multi-touch attribution using Shapley values, Markov chain removal effects, Bayesian HMC MMM
- Budget reallocation simulation
- 91% CI test coverage

### Concepts Worth Learning

- Removal-effect framing: "removing this ad reduces estimated conversions by X%"
- Test coverage discipline (91% is aspirational benchmark)

### Parts Irrelevant to QualLoop

- Go language
- Multi-touch channel attribution
- Adstock and saturation modeling

### Ideas We Will Adapt

- Removal-effect framing for explaining pausing recommendations
- Test coverage discipline

### Ideas We Will Not Implement

- Shapley, Markov, or HMC attribution models in v1

---

## Repository 7 — meta-mcp-server (oliverames)

**URL:** https://github.com/oliverames/meta-mcp-server  
**Accessible:** YES  
**License:** MIT  
**Language:** TypeScript (Node.js)  
**Version:** v2.0.2, Graph API v21.0  
**Tools:** 199 tools across 7 Meta platforms

### Files Inspected

- `README.md` — 286 lines (complete tool reference)

### What Is Actually Present

- MCP server wrapping Meta Graph API v21.0
- CAPI tool: `meta_send_conversion_event` — confirms payload fields
- Campaign management, pixel management, token debugging

### Relevant CAPI Observations

CAPI payload shape confirmed: event_name, event_time (Unix timestamp),
user_data (hashed), custom_data, action_source (`website`).
Graph API v21.0 is current.

### Concepts Worth Learning

- Abstraction boundary: API authentication separate from tool logic
- Error message design: specific actionable errors, not raw codes
- Token/permission boundary documentation

### Ideas We Will Adapt

- Payload structure (event_name, event_time, user_data with hashed fields)
- Separation of payload construction from transmission
- Validation-before-send discipline

### Ideas We Will Not Implement

- MCP server protocol
- Live CAPI transmission in development

---

## Summary Table

| Repo | Accessible | License | Language | Primary Value for QualLoop |
|------|-----------|---------|----------|----------------------------|
| piperun-meta-capi-webhook | YES | None (do not copy) | JS/Node | Event mapping, PII hashing |
| bayesian-marketing-attribution | YES | None stated | Python | Beta-Binomial model, credible intervals |
| marketing-mix-allocation | YES | AGPL-3.0 | Python | Audit trail design, limitation framing |
| OpenCRM | YES | MIT | Python/Flask | Lead lifecycle states, campaign attribution |
| real-estate-lead-automation | YES | Unknown | n8n | Idempotent processing, signal/score separation |
| Attributor | YES | MIT | Go | Removal-effect framing, CI discipline |
| meta-mcp-server | YES | MIT | TypeScript | CAPI payload structure, API abstraction |

---

## Key Design Decisions Informed by Research

1. **Statistical model**: Beta-Binomial with uniform prior Beta(1,1), credible
   intervals via `scipy.stats.beta.interval` — informed by Repo 2.

2. **Separation of payload construction from transmission**: all Meta CAPI code
   builds and validates payloads without sending them — informed by Repo 1 and Repo 7.

3. **PII hashing**: SHA-256 on normalized email/phone before any external payload —
   informed by Repo 1. QualLoop uses synthetic data so this applies to future
   real-mode only.

4. **Lead lifecycle states** (not a simple pass/fail binary): informed by Repo 4 and
   Repo 5. QualLoop models `submitted | pending_contact | contacted |
   pending_qualification | qualified | disqualified | unresolved`.

5. **Audit trail with full evidence**: every decision record stores inputs, estimates,
   uncertainty intervals, policy version, and reasoning — informed by Repo 3.

6. **No code copied from Repo 1** (no license). Concepts noted only.

7. **AGPL notice for Repo 3**: no code used from Alloc Signal. Architecture patterns
   are general software engineering practices, not protectable expression.
