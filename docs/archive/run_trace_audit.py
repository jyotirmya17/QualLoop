import json
from pathlib import Path
from collections import Counter

with open("scratch/policy_ablation_results_v1.json", "r", encoding="utf-8") as f:
    d = json.load(f)

evals = d["eval_results"]
ads_a = {a["ad_id"]: a for a in evals["A"]["ad_records"]}
ads_b = {a["ad_id"]: a for a in evals["B"]["ad_records"]}
ads_c = {a["ad_id"]: a for a in evals["C"]["ad_records"]}
ads_d = {a["ad_id"]: a for a in evals["D"]["ad_records"]}

print(f"Total ads: {len(ads_a)}")

# Check identity between B, C, D across all 450 ads
diff_bc_paused = [ad_id for ad_id in ads_a if ads_b[ad_id]["paused_day"] != ads_c[ad_id]["paused_day"]]
diff_cd_paused = [ad_id for ad_id in ads_a if ads_c[ad_id]["paused_day"] != ads_d[ad_id]["paused_day"]]
diff_bc_spend = [ad_id for ad_id in ads_a if ads_b[ad_id]["spend"] != ads_c[ad_id]["spend"]]
diff_bc_ql = [ad_id for ad_id in ads_a if ads_b[ad_id]["m1_ql"] != ads_c[ad_id]["m1_ql"]]

print(f"Paused day differences B vs C: {len(diff_bc_paused)}")
print(f"Paused day differences C vs D: {len(diff_cd_paused)}")
print(f"Spend differences B vs C: {len(diff_bc_spend)}")
print(f"QL differences B vs C: {len(diff_bc_ql)}")

# Ads paused at Day 14 in A, delayed or missed in B/C/D
delayed_ads = [ad_id for ad_id in ads_a if ads_a[ad_id]["paused_day"] == 14 and ads_b[ad_id]["paused_day"] != 14]
print(f"\nTotal ads paused at Day 14 in A, delayed/missed in B/C/D: {len(delayed_ads)}")

# Group delayed ads by what happened in B/C/D
delayed_to_21 = [ad_id for ad_id in delayed_ads if ads_b[ad_id]["paused_day"] == 21]
missed_in_bcd = [ad_id for ad_id in delayed_ads if ads_b[ad_id]["paused_day"] is None]
print(f"  - Paused at Day 21 in B/C/D: {len(delayed_to_21)}")
print(f"  - Never paused (missed) in B/C/D: {len(missed_in_bcd)}")

# Sample traces of delayed ads
print("\n=== REPRESENTATIVE TRACES: ADS DELAYED FROM DAY 14 TO DAY 21 ===")
for ad_id in delayed_to_21[:5]:
    a = ads_a[ad_id]
    b = ads_b[ad_id]
    pd_a = a["pause_details"]
    pd_b = b["pause_details"]
    print(f"\nAd ID: {ad_id} | Family: {a['family']} | Scenario: {a['scenario_name']} | Seed: {a['seed']}")
    print(f"  True Intent: {a['true_intent']:.4f} | Label: {a['label']} | Ground Truth: {'Good' if a['is_good'] else 'Poor'}")
    print(f"  Policy A (Pause at Day 14): N_contacts={pd_a['n_mature_contacts']}, k_qual={pd_a['k_qualified']}, CI_high={pd_a['qual_ci_high']:.4f}")
    print(f"    Reason A: {pd_a['reason']}")
    print(f"  Policy B/C/D (Pause at Day 21): N_contacts={pd_b['n_mature_contacts']}, k_qual={pd_b['k_qualified']}, CI_high={pd_b['qual_ci_high']:.4f}")
    print(f"    Reason B: {pd_b['reason']}")

print("\n=== REPRESENTATIVE TRACES: ADS PAUSED IN A AT DAY 14 BUT MISSED IN B/C/D ===")
for ad_id in missed_in_bcd[:5]:
    a = ads_a[ad_id]
    b = ads_b[ad_id]
    pd_a = a["pause_details"]
    print(f"\nAd ID: {ad_id} | Family: {a['family']} | Scenario: {a['scenario_name']} | Seed: {a['seed']}")
    print(f"  True Intent: {a['true_intent']:.4f} | Label: {a['label']} | Ground Truth: {'Good' if a['is_good'] else 'Poor'}")
    print(f"  Policy A (Paused Day 14): N_contacts={pd_a['n_mature_contacts']}, k_qual={pd_a['k_qualified']}, CI_high={pd_a['qual_ci_high']:.4f}")
    print(f"  Policy B/C/D: Never reached N_contacts >= 20 by Day 21 -> Never paused! Full spend: Rs {b['spend']:.2f}")

# Check False Pauses
print("\n=== FALSE PAUSES ANALYSIS (GOOD ADS PAUSED) ===")
fps_a = [ad_id for ad_id in ads_a if ads_a[ad_id]["is_good"] and ads_a[ad_id]["paused_day"] is not None]
fps_b = [ad_id for ad_id in ads_a if ads_b[ad_id]["is_good"] and ads_b[ad_id]["paused_day"] is not None]
print(f"Policy A False Pauses: {len(fps_a)}")
print(f"Policy B/C/D False Pauses: {len(fps_b)}")

fp_rescued = [ad_id for ad_id in fps_a if ad_id not in fps_b]
fp_persisted = [ad_id for ad_id in fps_a if ad_id in fps_b]
fp_new = [ad_id for ad_id in fps_b if ad_id not in fps_a]
print(f"  - False pauses rescued in B/C/D: {len(fp_rescued)}")
print(f"  - False pauses persisting in B/C/D: {len(fp_persisted)}")
print(f"  - New false pauses created in B/C/D: {len(fp_new)}")

for ad_id in fp_rescued:
    a = ads_a[ad_id]
    b = ads_b[ad_id]
    pd_a = a["pause_details"]
    print(f"\n[RESCUED FALSE PAUSE] Ad ID: {ad_id} | Seed: {a['seed']} | True Intent: {a['true_intent']:.4f}")
    print(f"  Policy A paused at Day 14: N_contacts={pd_a['n_mature_contacts']}, k_qual={pd_a['k_qualified']}, CI_high={pd_a['qual_ci_high']:.4f}")
    print(f"  Policy B/C/D avoided pause at Day 14 because N_contacts < 20. By Day 21, qualifications recovered!")

for ad_id in fp_persisted[:3]:
    a = ads_a[ad_id]
    b = ads_b[ad_id]
    pd_a = a["pause_details"]
    pd_b = b["pause_details"]
    print(f"\n[PERSISTING FALSE PAUSE] Ad ID: {ad_id} | Seed: {a['seed']} | True Intent: {a['true_intent']:.4f}")
    print(f"  Policy A paused Day {a['paused_day']}: N_contacts={pd_a['n_mature_contacts']}, k={pd_a['k_qualified']}, CI_high={pd_a['qual_ci_high']:.4f}")
    print(f"  Policy B/C/D paused Day {b['paused_day']}: N_contacts={pd_b['n_mature_contacts']}, k={pd_b['k_qualified']}, CI_high={pd_b['qual_ci_high']:.4f}")
