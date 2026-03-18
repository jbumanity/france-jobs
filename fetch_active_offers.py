"""
Récupère le nombre d'offres actives (contrats de travail E1) par code ROME
via l'API Offres d'emploi v2 de France Travail.

Produit active_offers.json avec un comptage par code ROME.

Usage:
    uv run python fetch_active_offers.py
"""

import json
import os
import time
from datetime import datetime

import httpx


API_TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
API_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


def get_token():
    """Obtient un token OAuth2 via client_credentials."""
    # Charger .env
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k] = v

    r = httpx.post(
        API_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["FRANCE_TRAVAIL_CLIENT_ID"],
            "client_secret": os.environ["FRANCE_TRAVAIL_CLIENT_SECRET"],
            "scope": "api_offresdemploiv2 o2dsoffre",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    with open("occupations.json", encoding="utf-8") as f:
        occupations = json.load(f)

    codes = [o["code_rome"] for o in occupations]
    print(f"{len(codes)} codes ROME à interroger")

    results = {}
    errors = 0
    start = time.time()

    for i, code in enumerate(codes):
        try:
            r = httpx.get(
                API_SEARCH_URL,
                params={"codeROME": code, "natureContrat": "E1", "range": "0-0"},
                headers=headers,
                timeout=15,
            )
            cr = r.headers.get("Content-Range", "")
            results[code] = int(cr.split("/")[-1]) if "/" in cr else 0
        except Exception as e:
            results[code] = 0
            errors += 1
            print(f"  ERR {code}: {e}")

        if (i + 1) % 200 == 0 or i == len(codes) - 1:
            elapsed = time.time() - start
            print(f"  [{i+1}/{len(codes)}] {elapsed:.0f}s — {errors} erreurs")

        time.sleep(0.12)

    # Écriture
    output = {
        "_meta": {
            "source": "API France Travail Offres d'emploi v2",
            "endpoint": "/offres/search?codeROME={code}&natureContrat=E1&range=0-0",
            "description": "Offres actives, contrats de travail uniquement (hors alternance/apprentissage/formation)",
            "fetched_at": datetime.now().isoformat(),
            "total_codes": len(results),
            "total_active_offers": sum(results.values()),
            "codes_with_zero": sum(1 for v in results.values() if v == 0),
            "errors": errors,
        },
        "counts": results,
    }

    with open("active_offers.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Stats
    total = sum(results.values())
    zeros = sum(1 for v in results.values() if v == 0)
    print(f"\nactive_offers.json écrit")
    print(f"  Total offres actives E1: {total:,}")
    print(f"  Codes avec offres > 0: {len(results) - zeros}/{len(results)}")
    print(f"  Codes à zéro: {zeros}")
    print(f"  Erreurs: {errors}")


if __name__ == "__main__":
    main()
