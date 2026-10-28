import json
import scipy.stats as stats

def wilson_ci(k, n, conf=0.95):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    z = stats.norm.ppf(1 - (1 - conf)/2)
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    spread = z * (p * (1 - p) / n + z**2 / (4 * n**2))**0.5 / denom
    return p, max(0.0, centre - spread), min(1.0, centre + spread)

with open("scratch/step_4d41_evaluation_results.json") as f:
    d = json.load(f)

for k, v in d.items():
    print(f"=== {k}: {v['name']} ===")
    p, low, high = wilson_ci(v["false_pauses_015"], v["good_ads_015"])
    print(f"  FP @ 0.15: {v['false_pauses_015']}/{v['good_ads_015']} = {p*100:.2f}% [{low*100:.2f}%, {high*100:.2f}%]")
    p, low, high = wilson_ci(v["missed_poor_015"], v["poor_ads_015"])
    print(f"  Missed @ 0.15: {v['missed_poor_015']}/{v['poor_ads_015']} = {p*100:.2f}% [{low*100:.2f}%, {high*100:.2f}%]")
    p, low, high = wilson_ci(v["false_pauses_010"], v["good_ads_010"])
    print(f"  FP @ 0.10: {v['false_pauses_010']}/{v['good_ads_010']} = {p*100:.2f}% [{low*100:.2f}%, {high*100:.2f}%]")
    p, low, high = wilson_ci(v["missed_poor_010"], v["poor_ads_010"])
    print(f"  Missed @ 0.10: {v['missed_poor_010']}/{v['poor_ads_010']} = {p*100:.2f}% [{low*100:.2f}%, {high*100:.2f}%]")
    print(f"  Spend on Poor @ 0.15: Rs {v['spend_on_poor_015']:,.2f}")
    print(f"  Spend on Poor @ 0.10: Rs {v['spend_on_poor_010']:,.2f}")
    print(f"  Total Spend: Rs {v['total_spend']:,.2f} | Total QL: {v['total_ql']} | CPQL: Rs {v['cpql']:.2f}")
    print(f"  Mean Pause Day: {v['mean_pause_day']:.2f} | Pause Counts: {v['pause_day_counts']}\n")
