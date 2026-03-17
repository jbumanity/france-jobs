"""
Fusionne occupations.csv et scores.json en docs/data.json pour le frontend.

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

    # Charger les stats
    with open("occupations.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Métiers: {len(rows)}")

    # Construire le JSON final
    data = []
    for row in rows:
        slug = row["slug"]
        score = scores.get(slug, {})

        projets = int(row["projets_recrutement"]) if row["projets_recrutement"] else None
        taux = float(row["taux_difficulte"]) if row["taux_difficulte"] else None

        data.append({
            "code_rome": row["code_rome"],
            "slug": slug,
            "title": row["title"],
            "grand_domaine_code": row["grand_domaine_code"],
            "grand_domaine": row["grand_domaine"],
            "domaine_pro": row["domaine_pro"],
            "projets_recrutement": projets,
            "taux_difficulte": taux,
            "is_digital": row["is_digital"] == "True",
            "transition_eco": row["transition_eco"] or None,
            "emploi_reglemente": row["emploi_reglemente"] == "N" or False,
            "url": row["url"],
            # Scores IA (None si pas encore scoré)
            "exposure": score.get("exposure"),
            "exposure_rationale": score.get("rationale"),
        })

    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Stats
    scored = sum(1 for d in data if d["exposure"] is not None)
    with_bmo = sum(1 for d in data if d["projets_recrutement"])
    total_projets = sum(d["projets_recrutement"] for d in data if d["projets_recrutement"])
    digital = sum(1 for d in data if d["is_digital"])

    print(f"\ndocs/data.json:")
    print(f"  Total métiers: {len(data)}")
    print(f"  Avec score IA: {scored}/{len(data)}")
    print(f"  Avec données BMO: {with_bmo}/{len(data)}")
    print(f"  Total projets recrutement: {total_projets:,}")
    print(f"  Métiers numériques: {digital}")

    if scored > 0:
        avg = sum(d["exposure"] for d in data if d["exposure"] is not None) / scored
        print(f"  Exposition IA moyenne: {avg:.1f}/10")


if __name__ == "__main__":
    main()
