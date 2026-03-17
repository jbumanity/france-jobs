"""
Parse les fichiers JSON ROME open data et génère :
- occupations.json : liste des 1584 métiers avec métadonnées
- pages/<code_rome>.md : texte de chaque fiche pour le scoring LLM

Usage:
    uv run python parse_rome.py
"""

import json
import os
import re

ROME_DIR = "rome_data"
PAGES_DIR = "pages"
os.makedirs(PAGES_DIR, exist_ok=True)


def load_json(filename, encoding="latin-1"):
    path = os.path.join(ROME_DIR, filename)
    with open(path, encoding=encoding) as f:
        return json.load(f)


def build_category_map():
    """Construit un dict code_rome -> (grand_domaine, domaine_pro) depuis l'arborescence."""
    arbo = load_json("unix_arborescence_principale_v460.json")
    main = arbo["arbo_principale"]

    category_map = {}
    for grand_domaine in main:
        gd_code = grand_domaine["code_metier"]  # "A", "B", ...
        gd_libelle = grand_domaine["libelle"]
        for domaine_pro in grand_domaine.get("liste_domaine_prof", []):
            dp_code = domaine_pro["code_metier"]  # "A11", "A12", ...
            dp_libelle = domaine_pro["libelle"]
            for metier in domaine_pro.get("liste_metier", []):
                code_rome = metier["code_rome"]
                category_map[code_rome] = {
                    "grand_domaine_code": gd_code,
                    "grand_domaine": gd_libelle,
                    "domaine_pro_code": dp_code,
                    "domaine_pro": dp_libelle,
                }
    return category_map


def build_transition_map():
    """Construit un dict code_rome -> flags de transition depuis le référentiel."""
    codes = load_json("unix_referentiel_code_rome_v460.json")
    return {
        item["code_rome"]: {
            "transition_eco": item.get("transition_eco"),
            "transition_num": item.get("transition_num"),
            "transition_demo": item.get("transition_demo"),
            "emploi_reglemente": item.get("emploi_reglemente"),
            "emploi_cadre": item.get("emploi_cadre"),
        }
        for item in codes
    }


def fiche_to_markdown(fiche):
    """Convertit une fiche JSON en texte Markdown pour le LLM."""
    rome = fiche["rome"]
    lines = []
    lines.append(f"# {rome['intitule']} ({rome['code_rome']})")
    lines.append("")

    # Appellations (autres noms du métier)
    appellations = fiche.get("appellations", [])
    if appellations:
        noms = [a["libelle"] for a in appellations[:10]]
        lines.append(f"**Autres appellations :** {', '.join(noms)}")
        lines.append("")

    # Définition
    definition = fiche.get("definition", "")
    if definition:
        lines.append("## Définition")
        lines.append(definition)
        lines.append("")

    # Accès au métier
    acces = fiche.get("acces_metier", "")
    if acces:
        lines.append("## Accès au métier")
        lines.append(acces)
        lines.append("")

    # Compétences (groupées)
    competences = fiche.get("competences", {})
    if competences:
        lines.append("## Compétences requises")
        # Handle both list and dict formats
        if isinstance(competences, list):
            for c in competences[:20]:
                if isinstance(c, dict):
                    lines.append(f"- {c.get('libelle', str(c))}")
                else:
                    lines.append(f"- {c}")
        elif isinstance(competences, dict):
            for groupe, items in list(competences.items())[:5]:
                lines.append(f"\n### {groupe}")
                if isinstance(items, list):
                    for item in items[:10]:
                        if isinstance(item, dict):
                            lines.append(f"- {item.get('libelle', str(item))}")
                        else:
                            lines.append(f"- {item}")
        lines.append("")

    # Contextes de travail
    contextes = fiche.get("contextes_travail", [])
    if contextes:
        lines.append("## Contextes de travail")
        if isinstance(contextes, list):
            for c in contextes[:15]:
                if isinstance(c, dict):
                    lines.append(f"- {c.get('libelle', str(c))}")
                else:
                    lines.append(f"- {c}")
        lines.append("")

    # Secteurs d'activité
    secteurs = fiche.get("secteurs_activite", [])
    if secteurs:
        lines.append("## Secteurs d'activité")
        if isinstance(secteurs, list):
            noms = [s.get("libelle", str(s)) if isinstance(s, dict) else str(s) for s in secteurs[:10]]
            lines.append(", ".join(noms))
        lines.append("")

    return "\n".join(lines)


def main():
    print("Chargement des données ROME...")
    category_map = build_category_map()
    transition_map = build_transition_map()

    print("Chargement des fiches métiers...")
    fiches = load_json("unix_fiche_emploi_metier_v460.json")
    print(f"  {len(fiches)} fiches chargées")

    occupations = []
    pages_written = 0

    for fiche in fiches:
        rome = fiche["rome"]
        code_rome = rome["code_rome"]
        libelle = rome["intitule"]

        # Slug (pour les noms de fichiers)
        slug = code_rome.lower()

        # Catégorie
        cat = category_map.get(code_rome, {})
        trans = transition_map.get(code_rome, {})

        # URL de la fiche publique
        url = f"https://candidat.francetravail.fr/metierscope/fiche-metier/{code_rome}"

        # Entrée dans occupations.json
        entry = {
            "code_rome": code_rome,
            "slug": slug,
            "title": libelle,
            "url": url,
            "grand_domaine_code": cat.get("grand_domaine_code", "?"),
            "grand_domaine": cat.get("grand_domaine", "Autre"),
            "domaine_pro_code": cat.get("domaine_pro_code", "?"),
            "domaine_pro": cat.get("domaine_pro", "Autre"),
            "transition_num": trans.get("transition_num"),
            "transition_eco": trans.get("transition_eco"),
            "emploi_reglemente": trans.get("emploi_reglemente"),
            "emploi_cadre": trans.get("emploi_cadre"),
            "nb_appellations": len(fiche.get("appellations", [])),
        }
        occupations.append(entry)

        # Écrire la page Markdown
        md_path = os.path.join(PAGES_DIR, f"{slug}.md")
        if not os.path.exists(md_path):
            md = fiche_to_markdown(fiche)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md)
            pages_written += 1

    # Sauvegarder occupations.json
    with open("occupations.json", "w", encoding="utf-8") as f:
        json.dump(occupations, f, ensure_ascii=False, indent=2)

    print(f"Écrit: occupations.json ({len(occupations)} métiers)")
    print(f"Écrit: {pages_written} pages Markdown dans pages/")

    # Stats rapides
    gd_counts = {}
    for occ in occupations:
        gd = occ["grand_domaine_code"]
        gd_counts[gd] = gd_counts.get(gd, 0) + 1
    print("\nDistribution par grand domaine:")
    for gd, count in sorted(gd_counts.items()):
        print(f"  {gd}: {count} métiers")

    # Transition numérique
    num_counts = {}
    for occ in occupations:
        v = occ.get("transition_num") or "Non classifié"
        num_counts[v] = num_counts.get(v, 0) + 1
    print("\nTransition numérique:")
    for k, v in sorted(num_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
