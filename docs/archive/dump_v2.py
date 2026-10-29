import json
from pathlib import Path

v2_p = Path("scratch/out_of_sample_results_v2.json")
with open(v2_p, "r", encoding="utf-8") as f:
    v2 = json.load(f)

for fam in ["continuous", "bimodal_synthetic", "preset", "OVERALL"]:
    print(f"*** Family: {fam} ***")
    for cfg in ["A", "C"]:
        st = v2["macro_summaries_by_family"][fam][cfg]
        print(f"  Cfg {cfg}: runs={st['n_runs']}, ads={st['n_ads']}, good={st['n_good']}, poor={st['n_poor']}, fp={st['false_pauses']} ({st['false_pause_rate']:.2%}), missed={st['missed_poor']} ({st['missed_poor_rate']:.2%}), poor_sp={st['poor_spend']}, tot_sp={st['total_spend']}, m1_ql={st['m1_pipeline_ql']}, cpql_m1={st['macro_cpql_m1_pipeline']}")
