import httpx
import json

if __name__ == "__main__":
    # 1. Run a simulation
    r = httpx.post("http://127.0.0.1:8000/simulations/run", json={"scenario_name": "mixed_portfolio", "seed": 42})
    print("Run simulation:", r.status_code)
    run = r.json()
    print("  run_id:", run["id"], "| n_ads:", run["n_ads"], "| n_leads:", run["n_leads"])

    # 2. Get ad analysis
    r2 = httpx.get(f"http://127.0.0.1:8000/ads/run/{run['id']}", timeout=30.0)
    print("Get analysis:", r2.status_code)
    campaigns = r2.json()
    for c in campaigns:
        print(f"  Campaign: {c['campaign_name']} | {c['n_ads']} ads | spend: {c['total_spend']}")
        for ad in c["ads"]:
            est = ad["estimate"]
            dec = ad["decision"]
            cid = ad["advertisement"]["creative_id"]
            print(f"    Ad {cid}:")
            print(f"      reach: {est['reachability_mean']:.1%} [{est['reachability_ci_low']:.1%},{est['reachability_ci_high']:.1%}]")
            print(f"      qual:  {est['qualification_mean']:.1%} [{est['qualification_ci_low']:.1%},{est['qualification_ci_high']:.1%}]")
            print(f"      eql:   {est['eql_mean']:.1f} [{est['eql_ci_low']:.1f},{est['eql_ci_high']:.1f}]")
            cpql = est["cpql_mean"]
            print(f"      cpql:  {cpql:.0f}" if cpql else "      cpql: unstable")
            print(f"      decision: {dec['action']} | confidence: {dec['confidence_level']}")
            print(f"      reason: {dec['reason'][:90]}...")

    # 3. List simulations
    r3 = httpx.get("http://127.0.0.1:8000/simulations/")
    print("\nList simulations:", r3.status_code, "| count:", len(r3.json()))

    # 4. Health
    r4 = httpx.get("http://127.0.0.1:8000/health")
    print("Health:", r4.status_code, r4.json())
