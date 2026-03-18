"""
Récupère les stats marché du travail pour chaque code ROME via l'API gw-metierscope.

Produit labour_market.json avec offres, demandeurs, salaires et tension par code ROME.

Usage:
    uv run python fetch_labour_market.py
"""

import json
import time
import httpx

API_BASE = "https://candidat.francetravail.fr/gw-metierscope/job"


def main():
    with open("occupations.json", encoding="utf-8") as f:
        occupations = json.load(f)

    print(f"{len(occupations)} métiers à interroger")

    client = httpx.Client(timeout=15)
    results = {}
    errors = []

    for i, occ in enumerate(occupations):
        code = occ["code_rome"]
        url = f"{API_BASE}/{code}/labourMarket?territory=FR"

        try:
            r = client.get(url)
            if r.status_code == 200:
                d = r.json()
                results[code] = {
                    "job_offers": d.get("jobOffers", {}).get("nombreIndicateur"),
                    "job_seekers": d.get("jobSeekers", {}).get("nombreIndicateur"),
                    "min_salary": d.get("salary", {}).get("minSalary"),
                    "max_salary": d.get("salary", {}).get("maxSalary"),
                    "period": d.get("jobOffers", {}).get("libellePeriode", ""),
                }
            else:
                errors.append(code)
                results[code] = {"job_offers": 0, "job_seekers": 0}
        except Exception as e:
            errors.append(code)
            results[code] = {"job_offers": 0, "job_seekers": 0}
            print(f"  ERR {code}: {e}")

        if (i + 1) % 100 == 0 or i == len(occupations) - 1:
            print(f"  [{i+1}/{len(occupations)}] {len(results)} OK, {len(errors)} erreurs")

        time.sleep(0.2)  # ~5 req/s

    client.close()

    with open("labour_market.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Stats
    offers = [v["job_offers"] for v in results.values() if v["job_offers"]]
    seekers = [v["job_seekers"] for v in results.values() if v["job_seekers"]]
    with_salary = sum(1 for v in results.values() if v.get("min_salary"))
    zeros = sum(1 for v in results.values() if not v["job_offers"])

    print(f"\nlabour_market.json écrit ({len(results)} métiers)")
    print(f"  Avec offres > 0 : {len(offers)}/{len(results)}")
    print(f"  Avec demandeurs > 0 : {len(seekers)}/{len(results)}")
    print(f"  Avec salaire : {with_salary}/{len(results)}")
    print(f"  Sans aucune offre : {zeros}")
    print(f"  Total offres : {sum(offers):,}")
    print(f"  Total demandeurs : {sum(seekers):,}")
    print(f"  Erreurs : {len(errors)}")


if __name__ == "__main__":
    main()
