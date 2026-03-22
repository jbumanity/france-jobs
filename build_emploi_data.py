"""
Agrege les donnees du recensement INSEE 2022 par profession PCS 2020.

Lit RP2022_indreg.parquet (lazy, colonnes selectionnees), calcule les stats
par profession, merge avec la nomenclature PCS et les scores IA, et produit
docs/emploi_data.json.

Usage:
    uv run python build_emploi_data.py
"""

import json
import os

import pandas as pd
import polars as pl

# ── Fichiers ──────────────────────────────────────────────────────────────────
PARQUET = "RP2022_indreg.parquet"
PCS_EXCEL = "Nomenclature_4Nemboites_PCS2020.xlsx"
SCORES_FILE = "emploi_scores.json"
OUTPUT = "docs/emploi_data.json"
PCS_CACHE = "pcs_professions.json"

# Colonnes a lire du parquet (11 sur 104)
READ_COLS = [
    "PROF", "IPONDI", "DIPL", "SEXE", "AGED",
    "EMPL", "TP", "STAT", "CS", "GS", "NA38",
]

# ── Labels fixes ──────────────────────────────────────────────────────────────
GROUP_LABELS = {
    "1": "Agriculteurs exploitants",
    "2": "Artisans, commerçants et chefs d'entreprise",
    "3": "Cadres et professions intellectuelles supérieures",
    "4": "Professions intermédiaires",
    "5": "Employés",
    "6": "Ouvriers",
}

# DIPL → (label, rank) — codage RP2022
DIPL_INFO = {
    "01": ("Pas de scolarité", 0),
    "02": ("Aucun diplôme", 1),
    "03": ("CEP", 2),
    "11": ("BEPC, brevet", 3),
    "12": ("CAP, BEP", 4),
    "13": ("Bac général", 5),
    "14": ("Bac techno/pro", 6),
    "15": ("Bac+2 (BTS, DUT)", 7),
    "16": ("Licence (Bac+3)", 8),
    "17": ("Maîtrise (Bac+4)", 9),
    "18": ("Bac+5 et plus", 10),
    "19": ("Doctorat", 11),
}

# NA38 → label secteur
NA38_LABELS = {
    "AZ": "Agriculture",
    "BZ": "Industries extractives",
    "CA": "Industrie alimentaire",
    "CB": "Textile, habillement",
    "CC": "Bois, papier, imprimerie",
    "CD": "Cokéfaction, raffinage",
    "CE": "Chimie",
    "CF": "Pharmacie",
    "CG": "Caoutchouc, plastique",
    "CH": "Métallurgie",
    "CI": "Informatique, électronique",
    "CJ": "Équipements électriques",
    "CK": "Machines, équipements",
    "CL": "Matériels de transport",
    "CM": "Autres industries manufacturières",
    "DZ": "Électricité, gaz",
    "EZ": "Eau, assainissement",
    "FZ": "Construction",
    "GZ": "Commerce",
    "HZ": "Transports, entreposage",
    "IZ": "Hébergement, restauration",
    "JA": "Édition, audiovisuel",
    "JB": "Télécommunications",
    "JC": "Informatique, services d'information",
    "KZ": "Finance, assurance",
    "LZ": "Immobilier",
    "MA": "Juridique, comptabilité, conseil",
    "MB": "Recherche-développement",
    "MC": "Publicité, marketing",
    "NZ": "Services administratifs et de soutien",
    "OZ": "Administration publique",
    "PZ": "Enseignement",
    "QA": "Santé humaine",
    "QB": "Hébergement médico-social et social",
    "RZ": "Arts, spectacles, activités récréatives",
    "SZ": "Autres activités de services",
    "TZ": "Activités des ménages employeurs",
    "UZ": "Activités extra-territoriales",
}


# ── Nomenclature PCS ─────────────────────────────────────────────────────────

def load_pcs_nomenclature() -> dict:
    """Charge la nomenclature PCS 2020 depuis l'Excel INSEE (ou cache)."""
    if os.path.exists(PCS_CACHE):
        with open(PCS_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  Cache PCS : {len(data)} entrees")
        return data

    print(f"  Lecture {PCS_EXCEL}...")
    df = pd.read_excel(PCS_EXCEL)
    print(f"  {len(df)} lignes, colonnes : {list(df.columns)}")

    # Excel: Niveau | code PCS2020 | Libellé long | libellé court
    # Niveau 1→6 groupes, 2→29 catégories, 3→121 regroupées, 4→311 professions
    # Le code est toujours 4 chars ; on extrait le préfixe selon le niveau.
    all_labels: dict[str, str] = {}

    for _, row in df.iterrows():
        niveau = row.iloc[0]
        raw_code = row.iloc[1]
        raw_label = row.iloc[2]

        if pd.isna(raw_code) or pd.isna(raw_label):
            continue

        full_code = str(raw_code).strip().lower()
        label = str(raw_label).strip()

        try:
            n = int(niveau)
        except (ValueError, TypeError):
            continue

        if n == 1:
            code = full_code[0]       # "1000" → "1"
        elif n == 2:
            code = full_code[:2]      # "2100" → "21"
        elif n == 3:
            code = full_code[:3]      # "10a0" → "10a"
        else:
            code = full_code          # "10a1" → "10a1"

        all_labels[code] = label

    print(f"  Labels extraits : {len(all_labels)} codes")
    by_len = {}
    for c in all_labels:
        by_len.setdefault(len(c), 0)
        by_len[len(c)] += 1
    print(f"  Par niveau : {dict(sorted(by_len.items()))}")

    # Construire les fiches profession (codes 3+ chars)
    professions = {}
    for code, label in all_labels.items():
        if len(code) < 3:
            continue
        group_code = code[0]
        cat_code = code[:2]
        professions[code] = {
            "code_pcs": code,
            "title": label,
            "group_code": group_code,
            "group_label": all_labels.get(group_code, GROUP_LABELS.get(group_code, "")),
            "category_code": cat_code,
            "category_label": all_labels.get(cat_code, ""),
        }

    with open(PCS_CACHE, "w", encoding="utf-8") as f:
        json.dump(professions, f, ensure_ascii=False, indent=2)

    print(f"  {len(professions)} professions PCS sauvees dans {PCS_CACHE}")
    return professions


# ── Utilitaires stats ─────────────────────────────────────────────────────────

def weighted_median(ages: list, weights: list):
    """Mediane ponderee."""
    if not ages or not weights:
        return None
    pairs = sorted(zip(ages, weights))
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    cumsum = 0
    for val, w in pairs:
        cumsum += w
        if cumsum >= total / 2:
            return int(val)
    return int(pairs[-1][0])


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Build emploi_data.json ===\n")

    # 1. Nomenclature PCS
    print("1. Nomenclature PCS 2020")
    pcs = load_pcs_nomenclature()

    # 2. Lecture parquet
    print(f"\n2. Lecture {PARQUET}...")
    if not os.path.exists(PARQUET):
        print(f"  ERREUR : {PARQUET} introuvable. Executer download_insee.py d'abord.")
        return

    schema = pl.scan_parquet(PARQUET).collect_schema()
    available = [c for c in READ_COLS if c in schema.names()]
    missing = set(READ_COLS) - set(available)
    if missing:
        print(f"  Colonnes absentes du parquet : {missing}")
    print(f"  Colonnes utilisees : {available}")

    # Scan lazy → filtre → collect
    print("  Chargement (lazy scan + filtre population active)...")
    df = (
        pl.scan_parquet(PARQUET)
        .select(available)
        .filter(pl.col("PROF").is_not_null())
        .collect()
    )

    # Cast toutes les colonnes en string sauf IPONDI et AGED
    str_cols = [c for c in available if c not in ("IPONDI", "AGED")]
    df = df.with_columns([pl.col(c).cast(pl.Utf8) for c in str_cols if c in df.columns])

    # Cast AGED en entier si necessaire
    if "AGED" in df.columns:
        df = df.with_columns(pl.col("AGED").cast(pl.Int64, strict=False))

    # Normaliser PROF en minuscules
    df = df.with_columns(pl.col("PROF").str.to_lowercase().str.strip_chars())

    # Filtrer population active (groupes 1-6 uniquement)
    df = df.filter(pl.col("PROF").str.contains(r"^[1-6]"))

    total_w = df["IPONDI"].sum()
    n_prof = df["PROF"].n_unique()
    print(f"  {len(df):,} individus -> {total_w:,.0f} personnes ponderees")
    print(f"  {n_prof} codes profession distincts")

    # Debug : valeurs uniques des colonnes cles
    for col in ["EMPL", "TP", "STAT", "DIPL"]:
        if col in df.columns:
            vals = df[col].drop_nulls().unique().sort().head(20).to_list()
            print(f"  {col} : {vals}")

    # 3. Agregations
    print("\n3. Agregation par profession...")

    # --- Statistiques de base (sommes ponderees) ---
    agg_exprs = [pl.col("IPONDI").sum().alias("employed")]

    if "SEXE" in df.columns:
        agg_exprs.append(
            (
                pl.when(pl.col("SEXE") == "2")
                .then(pl.col("IPONDI"))
                .otherwise(0)
                .sum()
                * 100
                / pl.col("IPONDI").sum()
            ).alias("pct_female")
        )

    if "TP" in df.columns:
        agg_exprs.append(
            (
                pl.when(pl.col("TP").str.starts_with("2"))
                .then(pl.col("IPONDI"))
                .otherwise(0)
                .sum()
                * 100
                / pl.col("IPONDI").sum()
            ).alias("pct_part_time")
        )

    if "EMPL" in df.columns:
        # CDI : EMPL commence par "1" (CDI, titulaire FP)
        agg_exprs.append(
            (
                pl.when(pl.col("EMPL").str.starts_with("1"))
                .then(pl.col("IPONDI"))
                .otherwise(0)
                .sum()
                * 100
                / pl.col("IPONDI").sum()
            ).alias("pct_cdi")
        )
        # CDD : EMPL commence par "2" (CDD, interim, apprenti)
        agg_exprs.append(
            (
                pl.when(pl.col("EMPL").str.starts_with("2"))
                .then(pl.col("IPONDI"))
                .otherwise(0)
                .sum()
                * 100
                / pl.col("IPONDI").sum()
            ).alias("pct_cdd")
        )
        # Non-salarie : EMPL commence par "3" ou STAT non-salarie
        agg_exprs.append(
            (
                pl.when(pl.col("EMPL").str.starts_with("3"))
                .then(pl.col("IPONDI"))
                .otherwise(0)
                .sum()
                * 100
                / pl.col("IPONDI").sum()
            ).alias("pct_independent")
        )

    basic = df.group_by("PROF").agg(agg_exprs)
    print(f"  Stats de base : {len(basic)} professions")

    # --- Mode pondere du diplome ---
    if "DIPL" in df.columns:
        dipl_mode = (
            df.filter(
                pl.col("DIPL").is_not_null()
                & ~pl.col("DIPL").is_in(["ZZ", "Z", ""])
            )
            .group_by(["PROF", "DIPL"])
            .agg(pl.col("IPONDI").sum().alias("w"))
            .sort(["PROF", "w"], descending=[False, True])
            .group_by("PROF")
            .first()
            .select(["PROF", pl.col("DIPL").alias("dom_dipl")])
        )
        basic = basic.join(dipl_mode, on="PROF", how="left")

    # --- Mode pondere du secteur ---
    if "NA38" in df.columns:
        sector_mode = (
            df.filter(
                pl.col("NA38").is_not_null()
                & ~pl.col("NA38").is_in(["ZZ", "Z", ""])
            )
            .group_by(["PROF", "NA38"])
            .agg(pl.col("IPONDI").sum().alias("w"))
            .sort(["PROF", "w"], descending=[False, True])
            .group_by("PROF")
            .first()
            .select(["PROF", pl.col("NA38").alias("dom_sector")])
        )
        basic = basic.join(sector_mode, on="PROF", how="left")

    # --- Mediane ponderee de l'age ---
    median_ages: dict[str, int] = {}
    if "AGED" in df.columns:
        print("  Calcul mediane d'age ponderee...")
        age_dist = (
            df.filter(pl.col("AGED").is_not_null())
            .group_by(["PROF", "AGED"])
            .agg(pl.col("IPONDI").sum().alias("w"))
            .sort(["PROF", "AGED"])
        )

        # Grouper par PROF et calculer la mediane en Python
        current_prof = None
        ages_buf = []
        weights_buf = []

        for row in age_dist.iter_rows(named=True):
            if row["PROF"] != current_prof:
                if current_prof is not None and ages_buf:
                    m = weighted_median(ages_buf, weights_buf)
                    if m is not None:
                        median_ages[current_prof] = m
                current_prof = row["PROF"]
                ages_buf = []
                weights_buf = []
            ages_buf.append(row["AGED"])
            weights_buf.append(row["w"])

        # Dernier groupe
        if current_prof is not None and ages_buf:
            m = weighted_median(ages_buf, weights_buf)
            if m is not None:
                median_ages[current_prof] = m

        print(f"  Mediane d'age pour {len(median_ages)} professions")

    # 4. Scores IA
    scores: dict = {}
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE, encoding="utf-8") as f:
            for entry in json.load(f):
                scores[entry["code_pcs"]] = entry
        print(f"\n  Scores IA : {len(scores)} professions")
    else:
        print(f"\n  {SCORES_FILE} non trouve (executer score_emploi.py)")

    # 5. Construction JSON
    print("\n4. Construction JSON...")
    records = []

    for row in basic.iter_rows(named=True):
        code = row["PROF"]
        info = pcs.get(code, {})
        score = scores.get(code, {})

        # Diplome
        dipl_code = row.get("dom_dipl")
        if dipl_code and str(dipl_code) in DIPL_INFO:
            dipl_label, dipl_rank = DIPL_INFO[str(dipl_code)]
        else:
            dipl_label = str(dipl_code) if dipl_code else ""
            dipl_rank = -1

        # Secteur
        sector_code = row.get("dom_sector")
        sector_label = NA38_LABELS.get(str(sector_code), str(sector_code)) if sector_code else ""

        records.append({
            "code_pcs": code,
            "title": info.get("title", code),
            "group_code": info.get("group_code", code[0] if code else ""),
            "group_label": info.get(
                "group_label",
                GROUP_LABELS.get(code[0] if code else "", ""),
            ),
            "category_code": info.get("category_code", code[:2] if len(code) >= 2 else ""),
            "category_label": info.get("category_label", ""),
            "employed": round(row["employed"]),
            "pct_female": round(row.get("pct_female", 0), 1),
            "median_age": median_ages.get(code),
            "pct_cdi": round(row.get("pct_cdi", 0), 1),
            "pct_cdd": round(row.get("pct_cdd", 0), 1),
            "pct_independent": round(row.get("pct_independent", 0), 1),
            "pct_part_time": round(row.get("pct_part_time", 0), 1),
            "dominant_diploma": dipl_label,
            "diploma_rank": dipl_rank,
            "dominant_sector": sector_label,
            "exposure": score.get("exposure"),
            "exposure_rationale": score.get("rationale", ""),
        })

    records.sort(key=lambda r: r["employed"], reverse=True)

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    total_emp = sum(r["employed"] for r in records)
    print(f"\n=== {OUTPUT} : {len(records)} professions, {total_emp:,.0f} personnes ===")


if __name__ == "__main__":
    main()
