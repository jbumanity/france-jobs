"""
Score chaque métier ROME sur son exposition à l'IA via Mistral ou Gemini.

Lit les pages Markdown depuis pages/, envoie chacune au LLM avec un prompt
de scoring, et sauvegarde les scores dans scores.json (checkpoint incrémental).

Usage:
    uv run python score.py                              # Mistral par défaut
    uv run python score.py --provider gemini             # utiliser Gemini
    uv run python score.py --start 0 --end 100 --force   # test sur 100 métiers
"""

import argparse
import json
import os
import re
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

MISTRAL_MODEL = "mistral-small-latest"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

OUTPUT_FILE = "scores.json"

SYSTEM_PROMPT = """\
Tu es un expert analyste du marché du travail français. Tu évalues dans quelle mesure \
l'intelligence artificielle va transformer chaque métier.

Tu vas recevoir la description d'un métier du référentiel ROME (Répertoire Opérationnel \
des Métiers et des Emplois, France).

Note l'**Exposition IA** de ce métier sur une échelle de 0 à 10.

L'Exposition IA mesure : dans quelle mesure l'IA va transformer ce métier ? \
Considère à la fois les effets directs (l'IA automatise des tâches actuellement \
réalisées par des humains) et les effets indirects (l'IA rend chaque travailleur \
tellement productif que moins de personnes sont nécessaires).

Le signal clé est de savoir si le travail est fondamentalement numérique. Si le métier \
peut être exercé entièrement depuis un bureau avec un ordinateur — rédiger, coder, \
analyser, communiquer — alors l'exposition IA est élevée (7+), car les capacités de l'IA \
dans les domaines numériques progressent rapidement. À l'inverse, les métiers nécessitant \
une présence physique, des compétences manuelles ou des interactions humaines en temps réel \
dans le monde physique ont une barrière naturelle à l'exposition IA.

Utilise ces ancres pour calibrer ton score :

- **0–1 : Exposition minimale.** Le travail est presque entièrement physique, manuel, \
ou nécessite une présence humaine en temps réel dans des environnements imprévisibles. \
L'IA n'a pratiquement aucun impact sur le travail quotidien. \
Exemples : couvreur, maraîcher, plongeur commercial.

- **2–3 : Faible exposition.** Travail essentiellement physique ou relationnel. L'IA \
peut aider pour des tâches périphériques mineures (planification, paperasse) mais \
ne touche pas le cœur du métier. \
Exemples : électricien, plombier, pompier, aide-soignant.

- **4–5 : Exposition modérée.** Mélange de travail physique/relationnel et de \
travail de connaissance. L'IA peut significativement aider pour les parties de \
traitement de l'information mais une part substantielle du travail nécessite \
encore une présence humaine. \
Exemples : infirmier, policier, vétérinaire.

- **6–7 : Forte exposition.** Travail principalement de connaissance avec quelques \
besoins de jugement humain, relations ou présence physique. Les outils IA sont \
déjà utiles et les travailleurs utilisant l'IA peuvent être substantiellement \
plus productifs. \
Exemples : enseignant, manager, comptable, journaliste.

- **8–9 : Très forte exposition.** Le métier s'effectue presque entièrement sur \
ordinateur. Toutes les tâches principales — rédiger, coder, analyser, concevoir, \
communiquer — sont dans des domaines où l'IA s'améliore rapidement. Le métier \
fait face à une restructuration majeure. \
Exemples : développeur logiciel, designer graphique, traducteur, analyste de données, \
juriste assistant, rédacteur.

- **10 : Exposition maximale.** Traitement d'informations routinier, entièrement \
numérique, sans composante physique. L'IA peut déjà réaliser la plupart des tâches \
aujourd'hui. \
Exemples : opérateur de saisie, télévendeur.

Réponds UNIQUEMENT avec un objet JSON dans ce format exact, sans autre texte :
{
  "exposure": <0-10>,
  "rationale": "<2-3 phrases expliquant les facteurs clés>"
}\
"""


def build_market_block(occ: dict, labour_market: dict) -> str:
    """Construit le bloc de données marché à ajouter au contenu envoyé au LLM."""
    code = occ["code_rome"]
    market = labour_market.get(code, {})

    if not market:
        return ""

    cadre_map = {"O": "oui", "N": "non"}
    cadre = cadre_map.get(occ.get("emploi_cadre"), "inconnu")

    num_map = {"O": "oui", "N": "non"}
    transition_num = num_map.get(occ.get("transition_num"), "inconnu")

    transition_eco = occ.get("transition_eco") or "inconnu"

    lines = [
        "",
        "---",
        "## Données de marché (2025)",
        f"- Offres d'emploi (12 mois) : {market.get('job_offers', 'N/A')}",
        f"- Demandeurs d'emploi : {market.get('job_seekers', 'N/A')}",
        f"- Salaire brut mensuel : {market.get('min_salary', '?')}–{market.get('max_salary', '?')}€",
        f"- Domaine professionnel : {occ.get('domaine_pro', 'inconnu')}",
        f"- Emploi cadre : {cadre}",
        f"- Transition numérique : {transition_num}",
        f"- Transition écologique : {transition_eco}",
    ]
    return "\n".join(lines)


def parse_llm_response(content: str) -> dict:
    """Parse la réponse JSON du LLM, avec nettoyage markdown et fallback regex."""
    content = content.strip()

    # Nettoyer les balises markdown si présentes
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        content = content.strip()

    # Essai de parsing direct
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Fallback : extraire exposure et rationale par regex si JSON tronqué
    exposure_match = re.search(r'"exposure"\s*:\s*(\d+)', content)
    rationale_match = re.search(r'"rationale"\s*:\s*"([^"]*)', content)
    if exposure_match:
        return {
            "exposure": int(exposure_match.group(1)),
            "rationale": rationale_match.group(1)[:200] if rationale_match else "",
        }

    raise ValueError(f"Impossible de parser la réponse: {content[:100]}")


def score_occupation_gemini(client: httpx.Client, text: str) -> dict:
    """Envoie une description de métier à Gemini et retourne le score structuré."""
    response = client.post(
        GEMINI_API_URL,
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT + "\n\n---\n\n" + text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        },
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()
    content = data["candidates"][0]["content"]["parts"][0]["text"]
    return parse_llm_response(content)


def score_occupation_mistral(client: httpx.Client, text: str) -> dict:
    """Envoie une description de métier à Mistral et retourne le score structuré."""
    response = client.post(
        MISTRAL_API_URL,
        headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
        json={
            "model": MISTRAL_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
        },
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return parse_llm_response(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["mistral", "gemini"], default="mistral",
                        help="Fournisseur LLM (défaut: mistral)")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None,
                        help="Secondes entre requêtes (défaut: 1.5 mistral, 6.5 gemini)")
    parser.add_argument("--force", action="store_true",
                        help="Re-scorer même si déjà en cache")
    args = parser.parse_args()

    # Défaut delay selon le provider
    if args.delay is None:
        args.delay = 1.5 if args.provider == "mistral" else 6.5

    # Vérifier la clé API
    if args.provider == "mistral" and not MISTRAL_API_KEY:
        print("ERREUR: MISTRAL_API_KEY non définie dans .env")
        return
    if args.provider == "gemini" and not GEMINI_API_KEY:
        print("ERREUR: GEMINI_API_KEY non définie dans .env")
        return

    # Charger la liste des métiers
    with open("occupations.json", encoding="utf-8") as f:
        occupations = json.load(f)

    # Charger les données marché
    with open("labour_market.json", encoding="utf-8") as f:
        labour_market = json.load(f)

    subset = occupations[args.start:args.end]

    # Charger les scores existants (cache)
    scores = {}
    if os.path.exists(OUTPUT_FILE) and not args.force:
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            for entry in json.load(f):
                scores[entry["slug"]] = entry

    to_score = [occ for occ in subset if occ["slug"] not in scores]
    print(f"Provider : {args.provider} ({MISTRAL_MODEL if args.provider == 'mistral' else GEMINI_MODEL})")
    print(f"Métiers à scorer : {len(to_score)}/{len(subset)}")
    print(f"Déjà en cache : {len(scores)}")
    print(f"Délai entre requêtes : {args.delay}s (={60/args.delay:.0f} req/min)")
    print(f"Durée estimée : {len(to_score) * args.delay / 60:.0f} minutes")

    if not to_score:
        print("Tout est déjà scoré !")
        return

    score_fn = score_occupation_mistral if args.provider == "mistral" else score_occupation_gemini
    errors = []
    client = httpx.Client()

    for i, occ in enumerate(to_score):
        slug = occ["slug"]
        md_path = f"pages/{slug}.md"

        if not os.path.exists(md_path):
            print(f"  [{i+1}] SKIP {slug} (pas de page Markdown)")
            continue

        with open(md_path, encoding="utf-8") as f:
            text = f.read()

        # Enrichir avec les données marché
        text += build_market_block(occ, labour_market)

        print(f"  [{i+1}/{len(to_score)}] {occ['title'][:50]}...", end=" ", flush=True)

        try:
            # Retry jusqu'à 3 fois sur 429
            result = None
            for attempt in range(3):
                try:
                    result = score_fn(client, text)
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < 2:
                        wait = (attempt + 1) * 10  # attente progressive: 10s, 20s
                        print(f"429 rate limit, attente {wait}s...", end=" ", flush=True)
                        time.sleep(wait)
                    else:
                        raise
            if result:
                scores[slug] = {
                    "slug": slug,
                    "code_rome": occ["code_rome"],
                    "title": occ["title"],
                    **result,
                }
                print(f"exposure={result['exposure']}")
        except Exception as e:
            print(f"ERREUR: {e}")
            errors.append(slug)
            # Continue même en cas d'erreur

        # Checkpoint incrémental (sauvegarde après chaque score)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(list(scores.values()), f, ensure_ascii=False, indent=2)

        # Respecter la limite de taux
        if i < len(to_score) - 1:
            time.sleep(args.delay)

    client.close()

    print(f"\nTerminé. {len(scores)} métiers scorés, {len(errors)} erreurs.")
    if errors:
        print(f"Erreurs : {errors[:10]}")

    # Stats finales
    vals = [s for s in scores.values() if "exposure" in s]
    if vals:
        avg = sum(s["exposure"] for s in vals) / len(vals)
        distribution = {}
        for s in vals:
            bucket = s["exposure"]
            distribution[bucket] = distribution.get(bucket, 0) + 1

        print(f"\nExposition IA moyenne : {avg:.1f}/10 ({len(vals)} métiers)")
        print("Distribution:")
        for k in sorted(distribution):
            bar = "█" * distribution[k]
            print(f"  {k:2d}: {bar[:50]} ({distribution[k]})")


if __name__ == "__main__":
    main()
