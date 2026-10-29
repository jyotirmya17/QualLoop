# Decision Objective and Economic Model Specification

**Role:** Skeptical ML Evaluation Engineer  
**Date:** 2026-10-28  
**Task Type:** Specification and Audit Only. No production decision rules, defaults, migrations, or runtime behaviors modified; no threshold tuning; no benchmark sweep executed; no git commits created.  
**Deliverables:**
- Machine-Readable Spec: [`scratch/step_4d7_economic_model_specification.json`](file:///d:/Developer/qualloop/scratch/step_4d7_economic_model_specification.json)
- Specification Tests: [`backend/tests/test_step_4d7_spec.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d7_spec.py)
- Markdown Specification Report: [`scratch/step_4d7_economic_model_specification.md`](file:///d:/Developer/qualloop/scratch/step_4d7_economic_model_specification.md)

---

## 1. Business Objective Currently Implied by QualLoop

### 1.1 The Current Policy Structure
In [`backend/decision_engine/engine.py`](file:///d:/Developer/qualloop/backend/decision_engine/engine.py), QualLoop evaluates ad snapshots through a priority-ordered rule cascade:
1. **Rule 1:** Minimum maturity fraction ($f_{\text{mature}} \ge 0.60$)
2. **Rule 2:** Minimum mature reachability sample ($N_{\text{leads}} \ge 30$)
3. **Rule 3:** Minimum mature qualification sample ($N_{\text{contacts}} \ge 20$)
4. **Rule 4:** Anomaly detection on relative intent shift ($|\Delta \hat{q}| \le 0.30$)
5. **Rule 5:** Low reachability upper bound ($\theta_{\text{reach, high}} < 0.25 \implies$ `INVESTIGATE_LOW_REACHABILITY`)
6. **Rule 6:** Low qualification upper bound ($\theta_{\text{qual, high}} < 0.10 \implies$ `PAUSE_AD`)
7. **Rule 7:** Cross-ad spend shift (relative CPQL dominance)
8. **Rule 8:** High CPQL lower bound ($\text{CPQL}_{\text{low}} > 500.0 \implies$ warning/reallocation)
9. **Rule 9:** Target CPQL upper bound ($\text{CPQL}_{\text{high}} < 75.0 \implies$ budget raise)

### 1.2 The Implied Objective Function
QualLoop does **not** maximize expected business profit or return on ad spend (ROAS).  
Instead, the existing system implements a **heuristic constraint-satisfaction filter**:
$$\max_{\mathbf{x} \in \text{Campaigns}} \sum_{i} S_i \quad \text{subject to } \quad \theta_{\text{qual, high}}(i) \ge q^*, \quad \theta_{\text{reach, high}}(i) \ge r^*, \quad \text{CPQL}_{\text{low}}(i) \le 500.0$$

#### Fundamental Economic Defects of This Implied Objective:
1. **Rate Fetishization vs Economic Efficiency:** Rule 6 pauses any ad with $\theta_{\text{qual, high}} < 0.10$, regardless of how cheaply the ad acquired leads or whether its realized CPQL was outstanding.
2. **Asymmetric Rule Ordering:** Rule 6 terminates ads solely based on intermediate qualification intent ($q$), evaluated *before* the CPQL reallocation rules (Rules 7 and 8). An ad with low qualification rate ($q=0.08$) and cheap CPL (yielding profitable ₹200 CPQL) is killed by Rule 6 before CPQL rules are ever evaluated.
3. **Implicit Homogeneous Lead Valuation:** The Historical Phase regret model implicitly assumed that every qualified lead generated across all campaigns, creative formats, and buyer segments carries an identical, static dollar value $V_{\text{QL}}$.

---

## 2. Separation of Observable Quantities from Business Assumptions

To establish rigorous economic modeling, we must strictly separate telemetry that QualLoop directly measures from commercial assumptions imported from outside the simulation:

| Metric / Parameter | Formal Symbol | Status in QualLoop | Source / Measurement Mechanism | Role in Decision Pipeline |
|---|---|---|---|---|
| **Media Spend** | $S_i$ | **Directly Observable** | Ad platform billing telemetry (Meta/Google Ads API). | Cumulative media cost incurred by creative $i$. |
| **Leads Ingested** | $L_i$ | **Directly Observable** | Webhook / landing page form submission events. | Top-of-funnel lead count. |
| **Call Attempts** | $A_i$ | **Directly Observable** | Telephony / CRM dialer call logs. | Outbound dialing workload. |
| **Contacts Reached** | $C_i$ | **Directly Observable** | Call disposition logs (`ANSWERED`). | Reachability numerator ($r = C / L$). |
| **Qualified Leads** | $QL_i$ | **Directly Observable** | Sales rep disposition in CRM (`QUALIFIED`). | Qualification numerator ($q = QL / C$). |
| **Lead Arrival & Resolution Timestamps** | $t_{\text{lead}}, t_{\text{call}}, t_{\text{qual}}$ | **Directly Observable** | Event timestamps in database. | Maturity window evaluation. |
| **Downstream Deal Conversion Rate** | $p_{\text{deal}} = P(\text{Won} \mid QL)$ | **Unobservable Assumption** | **Absent from QualLoop.** Requires closed-won CRM integration. | Probability a qualified lead yields cash revenue. |
| **Gross Deal Value / Contract Revenue** | $R_{\text{deal}}$ | **Unobservable Assumption** | **Absent from QualLoop.** Requires ERP/billing integration. | Revenue received per closed won deal. |
| **Gross Contribution Margin Ratio** | $GM\%$ | **Unobservable Assumption** | **Absent from QualLoop.** Accounting financial standard. | Revenue minus COGS and fulfillment expenses. |
| **Variable Servicing & Telephony Cost** | $c_{\text{lead}}, c_{\text{call}}$ | **Unobservable Assumption** | **Absent from QualLoop.** Telephony vendor rates & SDR wages. | Cost of processing leads and placing call attempts. |
| **Delayed Outcome Attribution Window** | $T_{\text{attr}}$ | **Unobservable Assumption** | **Heuristically Set.** Set to 3 days (contact) and 7 days (qual). | Time window after which uncontacted leads are considered failed. |

---

## 3. Parameterized Expected-Contribution-Profit Objective

### 3.1 Formal Mathematical Formulation
Let an advertiser manage a portfolio of $M$ ad creatives running under policy $\pi$ over evaluation horizon $T$.  
The **Net Expected Contribution Profit** $\Pi(\pi)$ is:

$$\Pi(\pi) = \sum_{i=1}^M \left[ \sum_{k=1}^{QL_i(\pi)} V_{i, k} - S_i(\pi) - c_{\text{lead}} \cdot L_i(\pi) - c_{\text{call}} \cdot A_i(\pi) \right]$$

Where:
- $S_i(\pi)$ is media spend incurred on creative $i$ under policy $\pi$.
- $L_i(\pi)$ is leads generated by creative $i$.
- $A_i(\pi)$ is call attempts placed on leads from creative $i$.
- $V_{i, k}$ is the economic contribution margin of qualified lead $k$ from ad $i$:
  $$V_{i, k} = p_{\text{deal}}(i, \mathbf{x}_k) \cdot \left[ R_{\text{deal}}(i, \mathbf{x}_k) \times GM\%(i, \mathbf{x}_k) \right] - c_{\text{fulfill}}(i, \mathbf{x}_k)$$

### 3.2 Heterogeneous Lead Valuation
Qualified leads do **not** carry equal commercial value across campaigns:
- **Campaign Tier / Audience Segment:** High-intent search leads (targeting enterprise buyers) have higher deal conversion ($p_{\text{deal}} = 25\%$) and larger contract values ($R = ₹250,000$), yielding $V_{\text{QL}} \approx ₹50,000$.
- **Broad Top-of-Funnel Social Leads:** Broad interest targeting yields lower deal conversion ($p_{\text{deal}} = 3\%$) and smaller contract values ($R = ₹20,000$), yielding $V_{\text{QL}} \approx ₹500$.
- **Segmented Valuation Model:**
  $$V_{\text{QL}}(i) = \bar{p}_{\text{deal}, i} \cdot \overline{\text{Margin}}_i - \bar{c}_{\text{fulfill}, i}$$

### 3.3 True Economic Breakeven CPQL
For creative $i$ to generate positive expected contribution profit, its Cost per Qualified Lead must satisfy:
$$\mathbb{E}[\text{CPQL}_i] \le \text{CPQL}_i^* = V_{\text{QL}}(i) - \frac{c_{\text{lead}} + c_{\text{call}} \cdot \bar{a}_i}{r_i \cdot q_i}$$
where $\bar{a}_i = A_i / L_i$ is average call attempts per lead, $r_i$ is reachability rate, and $q_i$ is qualification rate.

---

## 4. How the 10% and 15% Hurdles Relate (and Fail to Relate) to the Economic Objective

### 4.1 Mathematical Derivation
By definition:
$$\text{CPQL}_i = \frac{S_i}{QL_i} = \frac{S_i}{L_i \cdot r_i \cdot q_i} = \frac{\text{CPL}_i}{r_i \cdot q_i}$$
where $\text{CPL}_i = S_i / L_i$ is the cost per ingested lead.

Setting realized CPQL equal to target CPQL $T$:
$$\frac{\text{CPL}_i}{r_i \cdot q_i} = T \iff \mathbf{q^*(i) = \frac{\text{CPL}_i}{r_i \cdot T}}$$

### 4.2 Why Static Qualification Hurdles Fail Economically
A fixed qualification hurdle ($q < 0.10$ or $q < 0.15$) is **cost-blind**—it completely ignores top-of-funnel acquisition cost ($\text{CPL}$) and reachability ($r$):

#### Proof by Counterexample 1: The False-Pause Trap (High-ROI Low-Intent Ad)
- **Parameters:** Creative A acquires leads cheaply: $\text{CPL} = ₹15.00$, reachability $r = 0.60$, target CPQL $T = ₹500.00$.
- **Breakeven Qualification Hurdle:**
  $$q^* = \frac{₹15.00}{0.60 \times ₹500.00} = \mathbf{0.05 \quad (5.0\%)}$$
- **Realized Performance:** Creative A converts at $q = 0.08$ (8.0%).
- **Realized CPQL:**
  $$\text{CPQL} = \frac{₹15.00}{0.60 \times 0.08} = \mathbf{₹312.50} \quad (\ll ₹500.00 \text{ target})$$
- **Economic Reality:** Creative A generates **₹187.50 of net profit per qualified lead**.
- **QualLoop Decision:** Under both the 10% and 15% static hurdles, Rule 6 observes $\theta_{\text{high}} < 0.10$ and **PAUSES Creative A**! QualLoop destroys a highly profitable campaign.

#### Proof by Counterexample 2: The Missed-Poor Trap (Capital-Destroying High-Intent Ad)
- **Parameters:** Creative B targets expensive keywords: $\text{CPL} = ₹90.00$, reachability $r = 0.60$, target CPQL $T = ₹500.00$.
- **Breakeven Qualification Hurdle:**
  $$q^* = \frac{₹90.00}{0.60 \times ₹500.00} = \mathbf{0.30 \quad (30.0\%)}$$
- **Realized Performance:** Creative B converts at $q = 0.18$ (18.0%).
- **Realized CPQL:**
  $$\text{CPQL} = \frac{₹90.00}{0.60 \times 0.18} = \mathbf{₹833.33} \quad (\gg ₹500.00 \text{ target})$$
- **Economic Reality:** Creative B **loses ₹333.33 on every qualified lead**.
- **QualLoop Decision:** Because $q = 0.18 > 0.10$ and $> 0.15$, Rule 6 considers Creative B "healthy" and **allows it to run indefinitely**! QualLoop burns capital on an unviable campaign.

> [!CAUTION]
> **Conclusion:** An ad qualification rate hurdle that is decoupled from CPL and target CPQL is mathematically incapable of optimizing economic profit.

---

## 5. Classification of the Day 14 Oracle as a Heuristic Comparator

In Historical Phase and 4D.6, the evaluation compared policies against a "Day 14 Oracle" that pauses poor ads ($q_{\text{true}} < \tau_{\text{biz}}$) at Day 14.  
**We formally classify this Day 14 Oracle as a HEURISTIC COMPARATOR, NOT a universal profit optimum.**

### Mathematical Proof of Non-Optimality:
1. **Arbitrary Time Boundary:** Day 14 was chosen because $3 \text{ days contact} + 7 \text{ days qual} = 10 \text{ days}$, making Day 14 the first discrete evaluation checkpoint where mature evidence exists. It has no intrinsic economic optimality.
2. **Failure under High Lead Value:**
   If $V_{\text{QL}} = ₹2,000$ and an ad with $q_{\text{true}} = 0.08$ produces qualified leads between Day 14 and Day 28 at an incremental CPQL of ₹800, terminating the ad at Day 14 foregoes $+₹1,200$ net profit per lead.
   This produced the **negative regret** mathematically audited in Historical Phase.
3. **Definition of the True Economic Profit Oracle:**
   A true economic oracle pauses ad $i$ at timestamp $t^*$ if and only if the expected marginal profit of continuing the campaign is negative:
   $$\mathbb{E}[\text{Marginal Profit}_i(t > t^*)] = V_{\text{QL}}(i) \cdot \Delta QL_i(t > t^*) - \Delta S_i(t > t^*) < 0$$
   Equivalently:
   $$\text{Marginal CPQL}_i(t > t^*) > V_{\text{QL}}(i)$$

---

## 6. Required Data & Sensitivity Analysis Specification

### 6.1 Data Required to Estimate $V_{\text{QL}}$
To transition QualLoop from heuristic thresholding to true economic optimization, marketing and finance must provide:
1. **Closed-Won Conversion Telemetry:** CRM deal pipeline tied to `lead_id` and `advertisement_id`.
2. **Realized Deal Value:** Net contract value / order revenue per closed customer.
3. **Product Contribution Margin:** Gross margin percentage net of direct fulfillment and onboarding costs.
4. **Telephony & SDR Cost:** Cost per call attempt and lead review.

### 6.2 Sensitivity Analysis Specification (While Telemetry is Unavailable)
While closed-won telemetry is unavailable, evaluations must evaluate policies over a structured sensitivity sweep:
1. **Parameter Range:** Sweep $V_{\text{QL}} \in [0.5 \times \text{target\_cpql}, 10.0 \times \text{target\_cpql}]$ (e.g. ₹50 to ₹2,500).
2. **Crossover Anchors:**
   - $V_{15, A}^* = \mathbf{₹883.65}$ (Config A vs PROD_P15 crossover)
   - $V_{10, A}^* = \mathbf{₹1,078.27}$ (Config A vs PROD_P10 crossover)
   - $V_{10, 15}^* = \mathbf{₹1,640.91}$ (PROD_P15 vs PROD_P10 crossover)
3. **Heterogeneous Valuation Testing:**
   Test bimodal value distributions where Brand/Tier 1 campaigns have $V_{\text{QL}} = 2.5 \times \bar{V}$ and Generic/Tier 2 campaigns have $V_{\text{QL}} = 0.6 \times \bar{V}$.

---

## 7. Recommended Success Criteria for the Next Experiment

Future policy evaluations must not declare victory based on false-pause rate alone. An experiment is successful if and only if it satisfies all of the following multi-objective criteria:

### 1. Primary Success Criterion: Net Economic Contribution Profit
$$\mathbb{E}[\Pi(\pi_{\text{new}})] - \mathbb{E}[\Pi(\pi_{\text{baseline}})] > 0$$
Measured across frozen paired seeds with a 95% bootstrap confidence interval strictly excluding zero.

### 2. Secondary Economic Guardrails
- **Portfolio Realized CPQL:** Must not exceed target CPQL ($₹500.00$) at portfolio scale.
- **Economic Regret Minimization:** Expected regret relative to the True Economic Profit Oracle must decrease by at least 15%.

### 3. Statistical & Operational Guardrails
- **False Pause Rate on Economically Viable Ads ($\text{CPQL} \le V_{\text{QL}}$):** $\le 2.0\%$ (95% CI upper bound $\le 3.5\%$).
- **Missed Poor Ad Rate on Economically Unviable Ads ($\text{CPQL} > V_{\text{QL}}$):** $\le 20.0\%$.
- **Spend Waste Ratio:** Spend incurred on unviable ads before termination must not exceed $1.5 \times \text{spend\_at\_maturity}$.
- **Decision Latency:** No increase in median pause day on clear poor ads ($q < 0.05$).

---

## 8. Specification Verification Tests

Automated tests in [`backend/tests/test_step_4d7_spec.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d7_spec.py) verify the internal mathematical consistency of this specification:
1. `test_breakeven_qualification_rate_derivation`: Verifies $q^* = \text{CPL} / (r \cdot T)$.
2. `test_counterexample_proofs_against_static_hurdles`: Formally verifies Counterexample 1 (cheap viable ad paused) and Counterexample 2 (expensive unviable ad missed).
3. `test_true_economic_oracle_condition`: Verifies marginal CPQL condition vs Day 14 heuristic.
4. `test_json_specification_schema_and_completeness`: Validates that [`scratch/step_4d7_economic_model_specification.json`](file:///d:/Developer/qualloop/scratch/step_4d7_economic_model_specification.json) exists and contains all required fields.

---

## 9. Conclusion
- Historical Phase formally establishes that static qualification rate thresholds (10% or 15%) are fundamentally misaligned with business contribution profit.
- The Day 14 oracle is rigorously classified as a heuristic comparator, not an economic ceiling.
- The decision engine's future evolution must transition from rate-only filtering to expected CPQL / contribution profit optimization anchored by confirmed commercial parameters.
- **Specification complete. No production code modified, no thresholds tuned, and no deployment proposed.**
