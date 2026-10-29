# Research Archive & Historical Artifacts

This directory contains historical exploratory prototypes, research scripts, policy ablation logs, and audit records generated during the iterative design and verification of QualLoop.

## Purpose & Scope

- **Exploratory Prototypes:** Contains early scratchpad implementations and boundary experiments (e.g. initial counterfactual evaluation scripts and heuristic comparison runners).
- **Audit Records:** Contains raw historical JSON trace dumps and mathematical reconciliation notes.
- **Production Separation:** No production code in `backend/` or `frontend/` imports or depends on files in this directory. Active decision rules reside in [`backend/decision_engine/`](../../backend/decision_engine/), Bayesian estimators in [`backend/estimator/`](../../backend/estimator/), and offline shadow evaluation in [`backend/shadow/`](../../backend/shadow/).
- **Authoritative Benchmark Status:** The definitive, reproducible benchmark suite is executed via `python backend/benchmark/run_all.py` and its verified output is maintained in [`backend/benchmark/results/REPORT.md`](../../backend/benchmark/results/REPORT.md). Unverified numbers or intermediate drafts in these historical research notes do not supersede the master benchmark results.
