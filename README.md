# France Jobs — Visualiseur du Marché de l'Emploi Français

Treemap interactif des 1 584 métiers du référentiel ROME 4.0, dimensionné par le nombre d'offres d'emploi actives en France.

**[Voir le site](https://jbumanity.github.io/france-jobs/)**

Inspiré par le [AI Exposure Map](https://karpathy.github.io/ai-jobs/) d'Andrej Karpathy pour le marché américain.

## Ce que montre la visualisation

- **Surface** = nombre d'offres d'emploi actives (contrats de travail, hors alternance)
- **Groupement** = 14 grands domaines ROME (A-N), avec labels et bordures
- **5 couches de couleur** switchables sans re-layout :
  - Grand Domaine (14 catégories)
  - Difficulté de recrutement (BMO 2025)
  - Transition numérique (ROME 4.0)
  - Exposition IA (scoring Gemini, en cours)
  - Transition écologique (ROME 4.0)

## Architecture

```
occupations.csv            Référentiel ROME 4.0 (1 584 métiers)
occupations.json           Même liste, format JSON
pages/*.md                 Fiches métier enrichies (descriptions, compétences, contexte)
                ↓
fetch_active_offers.py     API Offres d'emploi v2 → active_offers.json
fetch_labour_market.py     API Metierscope → labour_market.json
score.py                   Gemini 2.5 Flash → scores.json
                ↓
build_site_data.py         Fusion → docs/data.json
                ↓
docs/index.html            Treemap vanilla JS (squarify 2 passes, pas de D3)
docs/data.json             Données consommées par le front
```

## Sources de données

| Donnée | Source | API |
|--------|--------|-----|
| Métiers ROME 4.0 | France Travail | Metierscope |
| Offres actives | France Travail | Offres d'emploi v2, `natureContrat=E1` |
| Demandeurs d'emploi | France Travail | Metierscope `/labourMarket` |
| Salaires | France Travail | Metierscope `/labourMarket` |
| Difficulté recrutement | France Travail | BMO 2025 |
| Transition numérique | France Travail | ROME 4.0 (flag `is_digital`) |
| Transition écologique | France Travail | ROME 4.0 (classification emploi vert/blanc) |
| Exposition IA | Gemini 2.5 Flash | Scoring LLM sur fiches métier |

Voir [DATA.md](DATA.md) pour le détail des choix méthodologiques, notamment pourquoi on utilise les offres actives plutôt que le cumul 12 mois.

## Choix de conception

### Treemap hiérarchique à 2 passes

Le treemap utilise un algorithme squarify en vanilla JS (pas de D3) avec 2 passes :
1. **Passe 1** : les 14 grands domaines sont disposés dans le container, proportionnellement à leurs offres totales
2. **Passe 2** : les métiers sont disposés à l'intérieur de chaque groupe

Les métiers au sein de chaque groupe sont triés par domaine professionnel (code[:3]) pour un clustering visuel naturel des sous-familles.

### Offres actives vs cumul 12 mois

Le choix le plus structurant. L'API Metierscope fournit un cumul 12 mois glissants qui surestime le marché d'un facteur ×17 en moyenne (jusqu'à ×85 pour certains métiers). On utilise à la place l'API Offres d'emploi v2 qui renvoie les offres réellement actives au moment du snapshot.

Le filtre `natureContrat=E1` exclut l'apprentissage et la professionnalisation. Ce choix est motivé par la découverte que certains organismes de formation (ex: Walter Learning) publient massivement de fausses offres d'emploi qui sont en réalité du recrutement pour des formations en alternance.

### Scoring IA : Gemini 2.5 Flash

Chaque métier reçoit un score d'exposition IA de 0 à 10 via Gemini 2.5 Flash Lite. Le prompt utilise des ancres calibrées :
- 0-1 : métiers physiques (couvreur, maraîcher)
- 4-5 : mixtes (infirmier, policier)
- 8-9 : numériques (développeur, traducteur)
- 10 : purement routinier et numérique (saisie, télévendeur)

Le modèle reçoit la fiche métier complète (description, compétences, contexte de travail) depuis `pages/*.md` et produit un score + justification en 2-3 phrases.

Le scoring est incrémental : checkpoint après chaque métier, reprend automatiquement en cas d'interruption.

### Couches de couleur sans re-layout

Le switch de couche ne recompute pas le layout (coûteux avec 1 584 rectangles). Il re-colore les noeuds DOM existants et met à jour les bordures des groupes (colorées par domaine en mode Grand Domaine, neutres sinon).

## Utilisation

### Prérequis

```bash
# Python 3.11+ avec uv
brew install uv
```

### Credentials

Créer un fichier `.env` :
```
FRANCE_TRAVAIL_CLIENT_ID=...     # https://francetravail.io/data/api
FRANCE_TRAVAIL_CLIENT_SECRET=...
GEMINI_API_KEY=...               # https://aistudio.google.com/apikey
```

### Pipeline complet

```bash
# 1. Rafraîchir les offres actives (~5 min)
uv run python fetch_active_offers.py

# 2. Rafraîchir les données marché (~5 min)
uv run python fetch_labour_market.py

# 3. Scoring IA (incrémental, ~3h pour 1 584 métiers)
uv run python score.py

# 4. Construire le JSON final
uv run python build_site_data.py

# 5. Servir en local
cd docs && python -m http.server 8000
```

## Licence

Projet open source. Données France Travail sous licence ouverte.
