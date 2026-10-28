import json

with open("scratch/step_4d5_aligned_evaluation.json", "r", encoding="utf-8") as f:
    d = json.load(f)

for p_key, p_val in d.items():
    print("=" * 80)
    print(f"POLICY: {p_key} ({p_val['policy_name']})")
    print("=" * 80)
    for h_key, h_val in p_val["scoring_views"].items():
        print(f"\n--- SCORING VIEW: {h_key} (Hurdle = {h_val['hurdle']}) ---")
        print(f"  Good Ads: {h_val['good_ads']} | Poor Ads: {h_val['poor_ads']} (Total: {h_val['total_ads']})")
        print(f"  False Pauses: {h_val['false_pauses']}/{h_val['good_ads']} = {h_val['false_pause_rate']*100:.2f}% (95% CI: [{h_val['false_pause_ci95'][0]*100:.2f}%, {h_val['false_pause_ci95'][1]*100:.2f}%])")
        print(f"  Missed Poor: {h_val['missed_poor']}/{h_val['poor_ads']} = {h_val['missed_poor_rate']*100:.2f}% (95% CI: [{h_val['missed_poor_ci95'][0]*100:.2f}%, {h_val['missed_poor_ci95'][1]*100:.2f}%])")
        print(f"  Spend on Poor: Rs {h_val['spend_on_poor']:,.2f} (Paused: Rs {h_val['spend_before_pause_poor']:,.2f}, Missed: Rs {h_val['spend_on_missed_poor']:,.2f})")
        print(f"  Total Spend: Rs {h_val['total_spend']:,.2f} | Total QL (M1): {h_val['total_m1_ql']} (M2: {h_val['total_m2_ql']})")
        print(f"  Lost QL on Good Ads (M1): {h_val['lost_ql_m1']} (M2: {h_val['lost_ql_m2']})")
        print(f"  Portfolio CPQL (M1): Rs {h_val['cpql_m1']} | (M2): Rs {h_val['cpql_m2']}")
        print(f"  Mean Pause Day: {h_val['mean_pause_day']} | Pause Counts: {h_val['pause_day_counts']}")
        rf = h_val["regret_formula"]
        print(f"  Regret Formula: {rf['formula']}")
        print(f"    Spend Waste (A): Rs {rf['A_spend_waste_component']:,.2f} | Lost QL (B): {rf['B_lost_lead_component']}")
        print("  Regret Samples by V_QL:")
        for v in [100, 300, 500, 1000, 1500, 2000]:
            print(f"    V_QL = Rs {v}: Regret = Rs {h_val['regret_grid'][str(v)]:,.2f}")
        rd = h_val["run_distributions"]
        print(f"  Per-run Distributions: FP rate std = {rd['fp_rate_std']:.4f}, Missed rate std = {rd['mp_rate_std']:.4f}, Spend std = Rs {rd['spend_per_run_std']:,.2f}")
