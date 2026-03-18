# Sources de données et choix méthodologiques

## Vue d'ensemble du pipeline

```
occupations.csv          → métiers ROME 4.0 (1 584 fiches)
labour_market.json       → cumul offres/demandeurs 12 mois (API Metierscope)
active_offers.json       → offres actives temps réel (API Offres d'emploi v2)
scores.json              → scores exposition IA (Gemini 2.5 Flash)
        ↓
    build_site_data.py
        ↓
    docs/data.json       → fichier unique consommé par le front-end
```

## Taille des rectangles : `active_offers`

**Source** : API France Travail — Offres d'emploi v2
`GET /offres/search?codeROME={code}&natureContrat=E1&range=0-0`

Le header `Content-Range` renvoie le nombre total d'offres actives correspondant au code ROME.

**Filtre `natureContrat=E1`** : on ne retient que les **contrats de travail** (CDI, CDD, intérim, saisonnier). Sont exclus :
- `E2` — Contrats d'apprentissage
- `FS` — Contrats de professionnalisation
- `FA` — Actions de formation préalables au recrutement

### Pourquoi ce choix

L'ancienne source (`labour_market.json` via l'API Metierscope) fournit un **cumul sur 12 mois glissants** qui surestime massivement le nombre d'offres réelles :

| Métier | Offres actives (E1) | Cumul 12 mois (Metierscope) | Facteur |
|--------|--------------------:|----------------------------:|--------:|
| Comptable | 8 468 | 245 020 | ×29 |
| Cuisinier | 3 079 | 79 900 | ×26 |
| Dev web | 615 | 52 510 | ×85 |
| Vendeur | 3 971 | 76 030 | ×19 |
| Aide-soignant | 1 058 | 20 130 | ×19 |

Le cumul 12 mois inclut les offres expirées, pourvues, renouvelées et republié par les agences d'intérim. Le chiffre "offres actives" correspond au stock réel visible sur candidat.francetravail.fr.

### Offres partenaires

L'API inclut par défaut les offres partenaires (Indeed, Monster, etc.), ce qui donne une vision plus complète du marché que les seules offres déposées directement sur France Travail.

### Alternance et fausses offres

Certains organismes de formation (ex: Walter Learning) publient des offres déguisées en emplois qui sont en réalité du recrutement pour des formations en alternance. Le filtre `natureContrat=E1` exclut ces fausses offres. Leur proportion varie selon les métiers :

| Métier | % alternance/formation |
|--------|----------------------:|
| Cuisinier | 16% |
| Vendeur | 14% |
| Dev web | 8% |
| Aide-soignant | 3% |
| Comptable | 2% |
| Expert-comptable | 0% |

## Données conservées de l'ancien pipeline

- **`job_offers`** (cumul 12 mois) : conservé dans data.json pour référence, affiché en grisé dans le tooltip
- **`job_seekers`** (demandeurs d'emploi) : toujours affiché
- **`taux_difficulte`** (BMO 2025) : utilisé pour la couche "Difficulté de recrutement"
- **Salaires** : min/max brut mensuel (API Metierscope)

## Fraîcheur des données

| Donnée | Source | Fréquence de mise à jour |
|--------|--------|--------------------------|
| `active_offers` | `fetch_active_offers.py` | À rafraîchir avant chaque déploiement (~5 min) |
| `labour_market` | `fetch_labour_market.py` | Trimestrielle (suit la période Metierscope) |
| Scores IA | `score.py` | Incrémental (64 scorés sur 1 584) |

## Scripts

| Script | Rôle | Commande |
|--------|------|----------|
| `fetch_active_offers.py` | Snapshot offres actives E1 par ROME | `uv run python fetch_active_offers.py` |
| `fetch_labour_market.py` | Cumul 12 mois + salaires + demandeurs | `uv run python fetch_labour_market.py` |
| `build_site_data.py` | Fusion → `docs/data.json` | `uv run python build_site_data.py` |
| `score.py` | Scoring exposition IA (Gemini) | `uv run python score.py` |
