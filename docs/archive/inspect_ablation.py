import json

with open('scratch/policy_ablation_results_v1.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

print('=== NEVER-PAUSED BASELINE ===')
print(d['never_paused_reference_baseline'])

families = ['continuous', 'bimodal_synthetic', 'preset', 'OVERALL']

for fam in families:
    print(f'\n======================================================')
    print(f'FAMILY: {fam.upper()}')
    print(f'======================================================')
    f_data = d['macro_summaries'][fam]
    for c in ['A', 'B', 'C', 'D']:
        s = f_data[c]
        print(f"Config {c} (Runs={s['n_runs']}, Ads={s['n_ads']}, Good={s['n_good']}, Poor={s['n_poor']}):")
        print(f"  False Pauses: {s['false_pauses']} / {s['n_good']} ({s['false_pause_rate']:.2%}) | FP Days: {s['fp_pause_day_counts']}")
        print(f"  Missed Poor:  {s['missed_poor']} / {s['n_poor']} ({s['missed_poor_rate']:.2%}) | Paused Poor: {s['paused_poor']} | Poor Days: {s['poor_pause_day_counts']} | Median Poor Day: {s['median_pause_day_poor']}")
        print(f"  Poor Spend:   Rs {s['poor_spend']:,.2f} | Total Spend: Rs {s['total_spend']:,.2f}")
        print(f"  M1 QL:        {s['m1_pipeline_ql']} | M2 QL: {s['m2_at_pause_ql']}")
        print(f"  M1 CPQL:      Rs {s['macro_cpql_m1_pipeline']:.2f} | M2 CPQL: Rs {s['macro_cpql_m2_at_pause']:.2f}")
        print(f"  Mean Run CPQL:Rs {s['mean_per_run_cpql_m1']:.2f} | Zero QL Runs: {s['zero_ql_runs_count']} | IE: {s['insufficient_evidence_events']}")

    print(f"\n--- PAIRED DIFFERENCES FOR {fam.upper()} (relative to Baseline A) ---")
    paired = d['paired_statistics'][fam]
    for comp in ['B_minus_A', 'C_minus_A', 'D_minus_A']:
        print(f"  [{comp}]")
        for m in ['false_pauses', 'missed_poor_ads', 'poor_spend', 'total_spend', 'qualified_leads']:
            res = paired[comp][m]
            print(f"    {m:<18}: Mean Diff={res['mean_diff']:+.4f}, 95% CI={res['ci_95']}, p(paired-t)={res['p_paired_t']:.4e}, p(wilcoxon)={res['p_wilcoxon']:.4e}")
