import json

with open("scratch/step_4d6_regret_integrity_audit_v1.json", "r", encoding="utf-8") as f:
    d = json.load(f)

print("=== INDEPENDENTLY RECOMPUTED RESULTS ===")
for pol, views in d["results"].items():
    print(f"\n--- {pol} ---")
    for h_str, m in views.items():
        print(f"  {h_str}:")
        print(f"    Good: {m['n_good']}, Poor: {m['n_poor']} | FP: {m['fp_count']} ({m['fp_rate']*100:.2f}%), MP: {m['mp_count']} ({m['mp_rate']*100:.2f}%)")
        print(f"    Spend Good: Rs {m['spend_good']:,.2f}, Spend Poor: Rs {m['spend_poor']:,.2f}, Total: Rs {m['spend_total']:,.2f}")
        print(f"    Total QL (M1): {m['total_m1_ql']}, (M2): {m['total_m2_ql']}")
        print(f"    Good Lost QL: {m['good_lost_ql']}, Good Saved Spend: Rs {m['good_saved_spend']:,.2f}")
        print(f"    Poor Excess Spend: Rs {m['poor_excess_spend']:,.2f}, Poor Excess QL: {m['poor_excess_ql']}")
        print(f"    A (Spend Waste): Rs {m['A_spend_waste']:,.2f}, B (Lost Leads): {m['B_lost_leads']}")
        print(f"    Formula: Regret(V) = {m['A_spend_waste']:,.2f} + ({m['B_lost_leads']} * V)")

print("\n=== ALGEBRAIC CROSSOVERS ===")
for h_str, cross in d["crossovers"].items():
    print(f"\n  {h_str}:")
    for pair, c in cross.items():
        print(f"    {pair}: dA = Rs {c['dA']:,.2f}, dB = {c['dB']}, V* = Rs {c['V_star']:,.2f}")
