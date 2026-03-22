"""
Telecharge les donnees INSEE necessaires pour le dashboard emploi.

- RP2022_indreg.parquet (617 Mo) : microdata recensement 2022
- Nomenclature_4Nemboites_PCS2020.xlsx (27 Ko) : nomenclature PCS 2020

Usage:
    uv run python download_insee.py
"""

import os
import httpx


FILES = [
    {
        "url": "https://www.insee.fr/fr/statistiques/fichier/8590183/RP2022_indreg.parquet",
        "dest": "RP2022_indreg.parquet",
        "desc": "Recensement 2022 — individus regions",
    },
    {
        "url": "https://www.insee.fr/fr/statistiques/fichier/6051913/Nomenclature_4Nemboites_PCS2020.xlsx",
        "dest": "Nomenclature_4Nemboites_PCS2020.xlsx",
        "desc": "Nomenclature PCS 2020 (4 niveaux emboites)",
    },
]


def download(url: str, dest: str, desc: str):
    """Telecharge un fichier avec affichage de progression."""
    if os.path.exists(dest):
        size_mb = os.path.getsize(dest) / 1024 / 1024
        print(f"  {dest} existe deja ({size_mb:.0f} Mo) — skip")
        return

    print(f"\n  {desc}")
    print(f"  {url}")

    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0

        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    mb = downloaded / 1024 / 1024
                    total_mb = total / 1024 / 1024
                    print(
                        f"\r  {mb:.0f}/{total_mb:.0f} Mo ({pct:.1f}%)",
                        end="",
                        flush=True,
                    )
                else:
                    mb = downloaded / 1024 / 1024
                    print(f"\r  {mb:.0f} Mo", end="", flush=True)

    final_mb = os.path.getsize(dest) / 1024 / 1024
    print(f"\n  Sauve : {dest} ({final_mb:.0f} Mo)")


def main():
    print("=== Telechargement donnees INSEE ===")
    for f in FILES:
        download(**f)
    print("\nTermine.")


if __name__ == "__main__":
    main()
