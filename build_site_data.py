"""
Fusionne occupations.csv, scores.json et labour_market.json en docs/data.json.

Usage:
    uv run python build_site_data.py
"""

import csv
import json
import os

os.makedirs("docs", exist_ok=True)


def main():
    # Charger les scores IA (peut être vide ou partiel)
    scores = {}
    if os.path.exists("scores.json"):
        with open("scores.json", encoding="utf-8") as f:
            for entry in json.load(f):
                scores[entry["slug"]] = entry

    print(f"Scores chargés: {len(scores)}")

    # Charger les données marché du travail
    labour = {}
    if os.path.exists("labour_market.json"):
        with open("labour_market.json", encoding="utf-8") as f:
            labour = json.load(f)

    print(f"Données marché du travail: {len(labour)}")

    # Charger les stats
    with open("occupations.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Métiers: {len(rows)}")

    # Construire le JSON final
    data = []
    for row in rows:
        slug = row["slug"]
        code = row["code_rome"]
        score = scores.get(slug, {})
        lm = labour.get(code, {})

        taux = float(row["taux_difficulte"]) if row["taux_difficulte"] else None

        data.append({
            "code_rome": code,
            "slug": slug,
            "title": row["title"],
            "grand_domaine_code": row["grand_domaine_code"],
            "grand_domaine": row["grand_domaine"],
            "domaine_pro": row["domaine_pro"],
            "domaine_pro_code": code[:3],
            # Taille : offres d'emploi (source principale)
            "job_offers": lm.get("job_offers") or 0,
            "job_seekers": lm.get("job_seekers") or 0,
            "min_salary": lm.get("min_salary"),
            "max_salary": lm.get("max_salary"),
            # Anciennes données BMO (conservées pour la couche tension)
            "taux_difficulte": taux,
            "is_digital": row["is_digital"] == "True",
            "transition_eco": row["transition_eco"] or None,
            "url": row["url"],
            # Scores IA (None si pas encore scoré)
            "exposure": score.get("exposure"),
            "exposure_rationale": score.get("rationale"),
        })

    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Stats
    scored = sum(1 for d in data if d["exposure"] is not None)
    with_offers = sum(1 for d in data if d["job_offers"])
    total_offers = sum(d["job_offers"] for d in data)
    total_seekers = sum(d["job_seekers"] for d in data)
    with_salary = sum(1 for d in data if d["min_salary"])
    digital = sum(1 for d in data if d["is_digital"])

    print(f"\ndocs/data.json:")
    print(f"  Total métiers: {len(data)}")
    print(f"  Avec offres > 0: {with_offers}/{len(data)}")
    print(f"  Total offres: {total_offers:,}")
    print(f"  Total demandeurs: {total_seekers:,}")
    print(f"  Avec salaire: {with_salary}/{len(data)}")
    print(f"  Avec score IA: {scored}/{len(data)}")
    print(f"  Métiers numériques: {digital}")

    if scored > 0:
        avg = sum(d["exposure"] for d in data if d["exposure"] is not None) / scored
        print(f"  Exposition IA moyenne: {avg:.1f}/10")


if __name__ == "__main__":
    main()
