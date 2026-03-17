"""
Construit occupations.csv avec les statistiques par métier ROME.

Sources :
- BMO 2025 (France Travail) : projets de recrutement et difficulté (par FAP)
- Mapping FAP->ROME : par correspondance de texte + grand domaine

Métriques produites par code ROME :
- projets_recrutement : nombre de projets de recrutement (proxy taille)
- taux_difficulte : % de recrutements jugés difficiles (tension)
- transition_num : O/N (depuis ROME open data)
- transition_eco : label (depuis ROME open data)

Usage:
    uv run python fetch_stats.py
"""

import json
import csv
import re
from collections import defaultdict

# ── Chargement des données ────────────────────────────────────────────────────

def load_json(path, encoding="utf-8"):
    with open(path, encoding=encoding) as f:
        return json.load(f)


def load_bmo():
    with open("bmo_national.json", encoding="utf-8") as f:
        return json.load(f)


def normalize(text):
    """Normalise un texte pour la comparaison."""
    text = text.lower()
    text = re.sub(r"[éèêë]", "e", text)
    text = re.sub(r"[àâä]", "a", text)
    text = re.sub(r"[îï]", "i", text)
    text = re.sub(r"[ôö]", "o", text)
    text = re.sub(r"[ùûü]", "u", text)
    text = re.sub(r"[ç]", "c", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def word_overlap(a, b):
    """Score de chevauchement de mots entre deux textes normalisés."""
    wa = set(w for w in normalize(a).split() if len(w) > 3)
    wb = set(w for w in normalize(b).split() if len(w) > 3)
    if not wa or not wb:
        return 0
    return len(wa & wb) / max(len(wa), len(wb))


def build_fap_rome_mapping(occupations, bmo):
    """
    Construit un mapping FAP -> liste de ROME codes par correspondance de texte.
    Stratégie : pour chaque FAP, trouver les ROME avec le meilleur chevauchement de mots.
    On associe ensuite chaque ROME au FAP le plus proche.
    """
    print("Construction du mapping FAP->ROME par correspondance textuelle...")

    # Pour chaque ROME, calculer le meilleur FAP match
    rome_to_fap = {}

    for occ in occupations:
        code_rome = occ["code_rome"]
        rome_title = occ["title"]
        best_fap = None
        best_score = 0

        for fap_code, fap_data in bmo.items():
            fap_nom = fap_data.get("nom", "")
            score = word_overlap(rome_title, fap_nom)
            if score > best_score:
                best_score = score
                best_fap = fap_code

        rome_to_fap[code_rome] = {
            "fap_code": best_fap,
            "match_score": best_score,
        }

    # Mapping inversé : FAP -> liste de ROME codes
    fap_to_rome = defaultdict(list)
    for code_rome, match in rome_to_fap.items():
        if match["fap_code"]:
            fap_to_rome[match["fap_code"]].append(code_rome)

    # Stats du mapping
    matched = sum(1 for m in rome_to_fap.values() if m["match_score"] > 0.15)
    print(f"  {matched}/{len(occupations)} ROME codes matchés (score > 0.15)")

    return rome_to_fap


def main():
    print("Chargement des données...")
    occupations = load_json("occupations.json")
    bmo = load_bmo()

    print(f"  {len(occupations)} métiers ROME")
    print(f"  {len(bmo)} familles professionnelles BMO (FAP)")

    # Construire le mapping FAP->ROME
    rome_to_fap = build_fap_rome_mapping(occupations, bmo)

    # Construire le CSV final
    print("\nConstruction de occupations.csv...")
    rows = []

    for occ in occupations:
        code_rome = occ["code_rome"]
        match = rome_to_fap.get(code_rome, {})
        fap_code = match.get("fap_code")
        match_score = match.get("match_score", 0)

        # Stats BMO du FAP correspondant
        bmo_data = bmo.get(fap_code, {}) if fap_code else {}
        projets = bmo_data.get("met", 0)
        difficiles = bmo_data.get("xmet", 0)
        taux_difficulte = round(difficiles / projets * 100, 1) if projets > 0 else None

        # Transition numérique : "O" = oui, "N" = non, None = non classifié
        trans_num_raw = occ.get("transition_num")
        is_digital = (trans_num_raw == "O")

        rows.append({
            "code_rome": code_rome,
            "slug": occ["slug"],
            "title": occ["title"],
            "grand_domaine_code": occ["grand_domaine_code"],
            "grand_domaine": occ["grand_domaine"],
            "domaine_pro": occ["domaine_pro"],
            "projets_recrutement": projets,
            "taux_difficulte": taux_difficulte,
            "is_digital": is_digital,
            "transition_eco": occ.get("transition_eco") or "",
            "emploi_reglemente": occ.get("emploi_reglemente") or "",
            "fap_code": fap_code or "",
            "fap_match_score": round(match_score, 3),
            "url": occ["url"],
        })

    # Sauvegarder
    fieldnames = list(rows[0].keys())
    with open("occupations.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Écrit: occupations.csv ({len(rows)} lignes)")

    # Stats
    with_bmo = sum(1 for r in rows if r["projets_recrutement"] > 0)
    total_projets = sum(r["projets_recrutement"] for r in rows)
    with_difficulte = sum(1 for r in rows if r["taux_difficulte"] is not None)
    digital = sum(1 for r in rows if r["is_digital"])

    print(f"\nStats:")
    print(f"  Avec données BMO : {with_bmo}/{len(rows)}")
    print(f"  Total projets de recrutement : {total_projets:,}")
    print(f"  Avec taux de difficulté : {with_difficulte}/{len(rows)}")
    print(f"  Métiers numériques (transition_num=O) : {digital}")

    # Exemples des meilleurs matchs
    print("\nExemples de matchs FAP->ROME:")
    samples = sorted(
        [(r["code_rome"], r["title"], r["fap_code"], r["fap_match_score"]) for r in rows],
        key=lambda x: -x[3]
    )[:10]
    for code, title, fap, score in samples:
        fap_nom = bmo.get(fap, {}).get("nom", "?") if fap else "?"
        print(f"  [{score:.2f}] {code} '{title[:30]}' -> {fap} '{fap_nom[:30]}'")


if __name__ == "__main__":
    main()
