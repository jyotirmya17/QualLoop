# Economic-Regret Integrity Audit

**Role:** Skeptical ML Evaluation Engineer  
**Date:** 2026-10-28  
**Audit Scope:** Verification and integrity audit of Historical Phase regret equations, oracle definitions, algebraic crossovers, and metric accounting. No production decision rules, defaults, migrations, or runtime behaviors modified; no git commits created.  
**Deliverables:**
- Audit Results: [`scratch/step_4d6_regret_integrity_audit_v1.json`](file:///d:/Developer/qualloop/scratch/step_4d6_regret_integrity_audit_v1.json)
- Audit Script: [`scratch/audit_step_4d6.py`](file:///d:/Developer/qualloop/scratch/audit_step_4d6.py)
- Summary Script: [`scratch/print_audit_4d6.py`](file:///d:/Developer/qualloop/scratch/print_audit_4d6.py)
- Unit Tests: [`backend/tests/test_step_4d6_integrity.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d6_integrity.py)
- Comprehensive Audit Report: [`scratch/step_4d6_regret_integrity_audit_v1.md`](file:///d:/Developer/qualloop/scratch/step_4d6_regret_integrity_audit_v1.md)

---

## 1. Independent Recomputation of Regret Components

Every simulation run, ad observation, decision action, spend accumulation, and lead qualification was independently reconstructed from raw domain objects from scratch (190 runs, 450 total ads).

### 1.1 Decomposition of Regret Terms
$$\text{Regret}(\pi; V_{\text{QL}}) = A(\pi) + B(\pi) \cdot V_{\text{QL}}$$

Where:
- **Spend Waste Component ($A$, units: ₹):**
  $$A(\pi) = \text{Spend Waste on Poor Ads} - \text{Spend Saved on Good False Pauses}$$
  $$A(\pi) = \sum_{j \in \text{Poor}} \max(0, S_j(\pi) - S_j(\text{Oracle})) - \sum_{i \in \text{Good False Pauses}} (S_i(\text{Full}) - S_i(\pi))$$
- **Lost Qualified Lead Component ($B$, units: Qualified Leads):**
  $$B(\pi) = \text{Qualified Leads Lost on Good Ads} - \text{Excess Leads Generated on Poor Ads}$$
  $$B(\pi) = \sum_{i \in \text{Good False Pauses}} (QL_i(\text{Full}) - QL_i(\pi)) - \sum_{j \in \text{Poor}} \max(0, QL_j(\pi) - QL_j(\text{Oracle}))$$

### 1.2 Independently Recomputed Coefficients Table

| Policy | Scoring Hurdle ($\tau_{\text{biz}}$) | Poor Excess Spend ($₹$) | Good Saved Spend ($₹$) | Coefficient $A$ ($₹$) | Good Lost QL (leads) | Poor Excess QL (leads) | Coefficient $B$ (leads) | Reconstructed Regret Equation |
|---|---|---|---|---|---|---|---|---|
| **PROD_P10** | **0.10 (10%)** | ₹268,000.00 | ₹5,000.00 | **₹263,000.00** | 9 | 186 | **−177** | $\text{Regret}(V) = 263,000 - 177 \times V$ |
| **PROD_P10** | **0.15 (15%)** | ₹335,500.00 | ₹2,500.00 | **₹333,000.00** | 7 | 285 | **−278** | $\text{Regret}(V) = 333,000 - 278 \times V$ |
| **PROD_P15** | **0.10 (10%)** | ₹186,500.00 | ₹13,750.00 | **₹172,750.00** | 22 | 144 | **−122** | $\text{Regret}(V) = 172,750 - 122 \times V$ |
| **PROD_P15** | **0.15 (15%)** | ₹250,250.00 | ₹7,500.00 | **₹242,750.00** | 17 | 240 | **−223** | $\text{Regret}(V) = 242,750 - 223 \times V$ |
| **CONFIG_A_P15** | **0.10 (10%)** | ₹84,500.00 | ₹52,250.00 | **₹32,250.00** | 106 | 69 | **+37** | $\text{Regret}(V) = 32,250 + 37 \times V$ |
| **CONFIG_A_P15** | **0.15 (15%)** | ₹135,750.00 | ₹33,500.00 | **₹102,250.00** | 73 | 137 | **−64** | $\text{Regret}(V) = 102,250 - 64 \times V$ |

*Verification:* All numbers reconcile exactly with raw ad-level domain events. Total spend sums match:
$$\text{Spend}_{\text{Good}} + \text{Spend}_{\text{Poor}} = \text{Total Spend}$$
- PROD_P10: ₹1,505,000 + ₹653,000 = ₹2,158,000 (at 0.10); ₹1,367,500 + ₹790,500 = ₹2,158,000 (at 0.15).
- PROD_P15: ₹1,496,250 + ₹571,500 = ₹2,067,750 (at 0.10); ₹1,362,500 + ₹705,250 = ₹2,067,750 (at 0.15).
- CONFIG_A_P15: ₹1,457,750 + ₹469,500 = ₹1,927,250 (at 0.10); ₹1,336,500 + ₹590,750 = ₹1,927,250 (at 0.15).

---

## 2. Oracle Reference Audit

### 2.1 Oracle Characteristics & Constraints
1. **Ground Truth Knowledge:** The Oracle possesses **perfect, unconstrained knowledge of hidden true intent** ($q_{\text{true}}$). A real-world deployable online policy cannot possess this knowledge.
2. **Oracle Stopping Timing on Poor Ads:**
   - The Historical Phase Oracle stops poor ads ($q_{\text{true}} < \tau_{\text{biz}}$) at **Day 14** ($t_{\text{min}} = 14$).
   - *Rationale:* Day 14 was chosen as a practical data-mature benchmark because it matches the earliest checkpoint where both contact maturity (3 days) and qualification maturity (7 days) have elapsed.
   - *Theoretical vs Deployable:* An unconstrained theoretical oracle would pause poor ads at Day 0 ($S=0$). Stopping at Day 14 represents a "best possible policy constrained by observational maturity".
3. **Lead Attribution & Spend Accounting:** The Oracle preserves the identical sequential pipeline-harvest lead attribution (Metric 1: leads created before Day 14 that qualify post-pause are harvested).

### 2.2 Mathematical Explanation of Negative Regret
Notice that under both PROD_P10 and PROD_P15, the regret equations have **negative slopes** ($B < 0$), producing **negative regret** at high lead values (e.g., $V_{\text{QL}} > ₹1,500$):
- *Why does a policy produce negative regret against the Oracle?*
  Because the Oracle terminates poor ads at Day 14, it sacrifices all leads generated by poor ads between Day 14 and Day 28.
  Even for a poor ad with low intent (e.g., $q_{\text{true}} = 0.08$ or $0.12$), continuing to run between Day 14 and Day 28 still generates some qualifying leads (at a marginal cost of ~₹500 to ₹1,000 per lead).
  If business value $V_{\text{QL}} = ₹2,000$, paying ₹800 to acquire a lead from a "poor" ad yields a **net positive profit of +₹1,200**!
  Therefore, stopping poor ads at Day 14 was actually *suboptimal* for an advertiser whose lead value is ₹2,000.
  The policy that kept these marginal ads running harvested these leads and therefore achieved **higher total profit than the Day 14 Oracle**!
- *Conclusion:* Negative regret confirms that the Day 14 Oracle is a **fixed heuristic benchmark**, not an omniscient global profit ceiling across all possible values of $V_{\text{QL}}$.

---

## 3. Algebraic Derivation of Policy-Ranking Crossovers & Invariance Theorem

### 3.1 The Crossover Invariance Theorem
Between any two deployable policies $\pi_1$ and $\pi_2$, the difference in regret relative to the Oracle is:
$$\Delta \text{Regret}_{12}(V_{\text{QL}}) = \text{Regret}(\pi_1; V_{\text{QL}}) - \text{Regret}(\pi_2; V_{\text{QL}})$$
By definition of regret:
$$\text{Regret}(\pi_1) = \text{Profit}(\text{Oracle}) - \text{Profit}(\pi_1)$$
$$\text{Regret}(\pi_2) = \text{Profit}(\text{Oracle}) - \text{Profit}(\pi_2)$$
Subtracting the two equations:
$$\Delta \text{Regret}_{12}(V_{\text{QL}}) = [\text{Profit}(\text{Oracle}) - \text{Profit}(\pi_1)] - [\text{Profit}(\text{Oracle}) - \text{Profit}(\pi_2)] = \mathbf{\text{Profit}(\pi_2) - \text{Profit}(\pi_1)}$$

> [!IMPORTANT]
> **The Oracle profit cancels out completely.**  
> Furthermore, because $\text{Profit}(\pi) = V_{\text{QL}} \cdot QL(\pi) - \text{Spend}(\pi)$, we have:
> $$\Delta \text{Profit}_{12} = [S(\pi_1) - S(\pi_2)] - V_{\text{QL}} \cdot [QL(\pi_1) - QL(\pi_2)]$$
> The crossover value $V_{\text{QL}}^*$ where Policy 1 and Policy 2 have identical regret is:
> $$V_{\text{QL}}^* = \frac{S(\pi_1) - S(\pi_2)}{QL(\pi_1) - QL(\pi_2)}$$
> **Theorem:** The pairwise crossover points depend **only on the total realized spend and total realized qualified leads of the two policies**, and are **strictly invariant to the scoring hurdle $\tau_{\text{biz}}$ or the definition of the Oracle**!

### 3.2 Pairwise Crossover Calculations

#### Crossover 1: PROD_P15 vs CONFIG_A_P15
$$\Delta S = ₹2,067,750.00 - ₹1,927,250.00 = ₹140,500.00$$
$$\Delta QL = 5,171 - 5,012 = 159 \text{ leads}$$
$$V_{15, A}^* = \frac{₹140,500.00}{159} = \mathbf{₹883.65}$$

#### Crossover 2: PROD_P10 vs CONFIG_A_P15
$$\Delta S = ₹2,158,000.00 - ₹1,927,250.00 = ₹230,750.00$$
$$\Delta QL = 5,226 - 5,012 = 214 \text{ leads}$$
$$V_{10, A}^* = \frac{₹230,750.00}{214} = \mathbf{₹1,078.27}$$

#### Crossover 3: PROD_P10 vs PROD_P15
$$\Delta S = ₹2,158,000.00 - ₹2,067,750.00 = ₹90,250.00$$
$$\Delta QL = 5,226 - 5,171 = 55 \text{ leads}$$
$$V_{10, 15}^* = \frac{₹90,250.00}{55} = \mathbf{₹1,640.91}$$

---

### 3.3 Proven Three-Regime Policy Ranking

```
      CONFIG_A_P15 Optimal          PROD_P15 Optimal            PROD_P10 Optimal
<-----------------------------|---------------------------|---------------------------->
Rs 0                     Rs 883.65                   Rs 1,640.91                    V_QL
```

1. **Regime 1 ($V_{\text{QL}} < ₹883.65$): CONFIG_A_P15 is Strictly Optimal**
   - In low-margin businesses, saving ad spend on bad campaigns dominates lead loss.
   - Config A saves ₹140,500 to ₹230,750 in ad spend while sacrificing marginal leads whose acquisition cost exceeds their commercial value.
2. **Regime 2 ($₹883.65 \le V_{\text{QL}} \le ₹1,640.91$): PROD_P15 is Strictly Optimal**
   - In moderate-margin businesses, PROD_P15 achieves the optimal balance.
   - It captures 159 more leads than Config A at an effective marginal CPQL of ₹883.65, while eliminating 50 poor ads relative to PROD_P10.
3. **Regime 3 ($V_{\text{QL}} > ₹1,640.91$): PROD_P10 is Strictly Optimal**
   - In high-LTV enterprise businesses, qualified leads are extremely valuable.
   - PROD_P10's 0.38% false-pause rate preserves 55 additional leads over PROD_P15 at a marginal cost of ₹1,640.91. Since $V_{\text{QL}} > ₹1,640.91$, every preserved lead generates net profit.

---

## 4. Metric Consistency & Accounting Audit

1. **Partition Exhaustiveness:** Every single ad ($N=450$) is classified as either Good or Poor exactly once for each hurdle ($290 + 160 = 450$ at 0.10; $262 + 188 = 450$ at 0.15). No unlabelled gaps exist.
2. **Denominators Verified Against Raw Records:**
   - At $\tau = 0.10$: $N_{\text{good}} = 290$, $N_{\text{poor}} = 160$.
   - At $\tau = 0.15$: $N_{\text{good}} = 262$, $N_{\text{poor}} = 188$.
   - The shift of 28 ads corresponds exactly to campaigns with true intent $q_{\text{true}} \in [0.10, 0.15)$.
3. **Post-Decision Leakage Check:**
   - **Metric 1 (Pipeline Harvest):** Strict filter: `created_at < t_pause`. Evaluates lead pipeline in flight at decision time.
   - **Metric 2 (Strict Decision-Time):** Strict filter: `resolved_at <= t_pause`. Evaluates only fully resolved outcomes at checkpoint.
   - In no case are leads created after the pause timestamp credited.
4. **CPQL Accounting:** Portfolio macro CPQL ($\frac{\text{Total Spend}}{\text{Total QL}}$) is strictly separated from per-run average CPQL. Total spend matches the sum of spend on good and poor ads across all policies.

---

## 5. Separation of Verified Facts from Business Assumptions

| Category | Item | Verified Empirical Fact vs Business Assumption | Material Impact on Decision |
|---|---|---|---|
| **Fact** | Realized Spend & Qualified Leads | **Empirical Fact** (from 190 paired runs). | Fixes total cost and output of each policy. |
| **Fact** | Pairwise Crossover Values ($₹883.65, ₹1,640.91$) | **Mathematical Fact** ($\Delta \text{Spend} / \Delta \text{QL}$). | Fixes the exact boundaries where policy ranking reverses. |
| **Fact** | False Pause Rates (PROD_P10: 0.38%, Config A: 5.73%) | **Empirical Fact**. | Quantifies statistical conservatism vs aggression. |
| **Assumption** | Economic Value of a Qualified Lead ($V_{\text{QL}}$) | **Commercial Assumption** (Not in simulator). | **CRITICAL.** Completely determines whether Config A, PROD_P15, or PROD_P10 is optimal. |
| **Assumption** | Viability Hurdle ($\tau_{\text{biz}} = 0.10$ vs $0.15$) | **Business Assumption** (Marketing target). | Governs whether an ad with $q=0.12$ is categorized as a "good ad" or a "poor ad". |
| **Assumption** | Oracle Stopping Timing ($t_{\text{min}} = \text{Day } 14$) | **Methodological Assumption**. | Sets the reference baseline for regret, but cancels out of pairwise policy comparisons. |

---

## 6. Test Suite & Verification Results

1. **Targeted Regret Integrity Suite ([`backend/tests/test_step_4d6_integrity.py`](file:///d:/Developer/qualloop/backend/tests/test_step_4d6_integrity.py)):**
   - `test_pairwise_regret_crossover_invariance_to_scoring_hurdle`: Verified mathematical cancellation of Oracle profit and crossover invariance.
   - `test_three_economic_regimes`: Verified profit maximization and regret minimization across $V_{\text{QL}} \in \{500, 1200, 2000\}$.
   - `test_negative_regret_explanation`: Verified marginal CPQL mechanism on poor ads.
   - **Result: 3 passed in 0.07s.**
2. **Combined Semantics and Integrity Suite:**
   - `pytest backend/tests/test_step_4d5_semantics.py backend/tests/test_step_4d6_integrity.py`
   - **Result: 7 passed in 3.55s.**
3. **Full Backend Test Suite:**
   - `pytest backend/tests`
   - **Result: 179 passed, 1 warning in 52.61s.**
4. **Clean Git State:** Zero production code, defaults, or database migrations modified.

---

## 7. Audit Conclusion & Recommendation

1. **The Historical Phase regret formulation and crossover values are mathematically correct, algebraically robust, and independently verified.**
2. **The three-regime policy ranking is proven:**
   - If $V_{\text{QL}} < ₹883.65 \implies$ **Config A** minimizes regret.
   - If $₹883.65 \le V_{\text{QL}} \le ₹1,640.91 \implies$ **PROD_P15** minimizes regret.
   - If $V_{\text{QL}} > ₹1,640.91 \implies$ **PROD_P10** minimizes regret.
3. **No further policy tuning should occur without a confirmed commercial input for $V_{\text{QL}}$.** Tuning thresholds in the absence of $V_{\text{QL}}$ is arbitrary, as any of the three policies can be declared "optimal" simply by selecting a different commercial lead valuation.
4. **Audit complete. No deployment or code modifications proposed.**
