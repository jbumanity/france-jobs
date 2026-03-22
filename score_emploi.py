"""
Score chaque profession PCS 2020 sur son exposition a l'IA via Mistral.

Lit pcs_professions.json (genere par build_emploi_data.py), envoie le
contexte hierarchique au LLM, et sauvegarde dans emploi_scores.json
(checkpoint incremental).

Usage:
    uv run python score_emploi.py                      # Mistral par defaut
    uv run python score_emploi.py --start 0 --end 50   # Test sur 50
    uv run python score_emploi.py --force               # Re-scorer tout
"""

import argparse
import json
import os
import re
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL = "mistral-small-latest"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

PCS_FILE = "pcs_professions.json"
OUTPUT_FILE = "emploi_scores.json"

SYSTEM_PROMPT = """\
Tu es un expert analyste du marché du travail français. Tu évalues dans quelle mesure \
l'intelligence artificielle va transformer chaque profession.

Tu vas recevoir la description d'une profession du référentiel PCS 2020 \
(Professions et Catégories Socioprofessionnelles, INSEE).

Note l'**Exposition IA** de cette profession sur une échelle de 0 à 10.

L'Exposition IA mesure : dans quelle mesure l'IA va transformer cette profession ? \
Considère à la fois les effets directs (l'IA automatise des tâches actuellement \
réalisées par des humains) et les effets indirects (l'IA rend chaque travailleur \
tellement productif que moins de personnes sont nécessaires).

Le signal clé est de savoir si le travail est fondamentalement numérique. Si la profession \
peut être exercée entièrement depuis un bureau avec un ordinateur — rédiger, coder, \
analyser, communiquer — alors l'exposition IA est élevée (7+), car les capacités de l'IA \
dans les domaines numériques progressent rapidement. À l'inverse, les professions nécessitant \
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

- **8–9 : Très forte exposition.** La profession s'exerce presque entièrement sur \
ordinateur. Toutes les tâches principales — rédiger, coder, analyser, concevoir, \
communiquer — sont dans des domaines où l'IA s'améliore rapidement. La profession \
fait face à une restructuration majeure. \
Exemples : développeur logiciel, designer graphique, traducteur, analyste de données.

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


def parse_llm_response(content: str) -> dict:
    """Parse la reponse JSON du LLM, avec nettoyage markdown et fallback regex."""
    content = content.strip()

    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        )
        content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    exposure_match = re.search(r'"exposure"\s*:\s*(\d+)', content)
    rationale_match = re.search(r'"rationale"\s*:\s*"([^"]*)', content)
    if exposure_match:
        return {
            "exposure": int(exposure_match.group(1)),
            "rationale": rationale_match.group(1)[:200] if rationale_match else "",
        }

    raise ValueError(f"Impossible de parser la reponse: {content[:100]}")


def score_occupation_mistral(client: httpx.Client, text: str) -> dict:
    """Envoie une profession au LLM et retourne le score structure."""
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
    parser = argparse.ArgumentParser(
        description="Score exposition IA des professions PCS 2020"
    )
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument(
        "--delay", type=float, default=1.5,
        help="Secondes entre requetes (defaut: 1.5)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-scorer meme si deja en cache",
    )
    args = parser.parse_args()

    if not MISTRAL_API_KEY:
        print("ERREUR: MISTRAL_API_KEY non definie dans .env")
        return

    if not os.path.exists(PCS_FILE):
        print(f"ERREUR: {PCS_FILE} introuvable.")
        print("Executer d'abord : uv run python build_emploi_data.py")
        return

    with open(PCS_FILE, encoding="utf-8") as f:
        pcs_all = json.load(f)

    # Garder uniquement les codes profession (4 chars = niveau le plus fin)
    professions = sorted(
        [v for v in pcs_all.values() if len(v["code_pcs"]) == 4],
        key=lambda x: x["code_pcs"],
    )
    subset = professions[args.start : args.end]

    # Charger scores existants
    scores: dict = {}
    if os.path.exists(OUTPUT_FILE) and not args.force:
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            for entry in json.load(f):
                scores[entry["code_pcs"]] = entry

    to_score = [p for p in subset if p["code_pcs"] not in scores]

    print("=== Score emploi IA (PCS 2020) ===")
    print(f"Provider : Mistral ({MISTRAL_MODEL})")
    print(f"Professions a scorer : {len(to_score)}/{len(subset)}")
    print(f"Deja en cache : {len(scores)}")
    print(f"Delai : {args.delay}s ({60 / args.delay:.0f} req/min)")
    print(f"Duree estimee : {len(to_score) * args.delay / 60:.0f} minutes")
    print(f"Cout estime : ~${len(to_score) * 0.0002:.2f}")

    if not to_score:
        print("Tout est deja score !")
        return

    errors = []
    client = httpx.Client()

    for i, prof in enumerate(to_score):
        code = prof["code_pcs"]
        title = prof["title"]

        # Contexte hierarchique pour le LLM
        text = (
            f"Profession : {title}\n"
            f"Code PCS 2020 : {code}\n"
            f"Groupe socioprofessionnel : {prof.get('group_label', '')}\n"
            f"Catégorie : {prof.get('category_label', '')}"
        )

        print(f"  [{i + 1}/{len(to_score)}] {title[:50]}...", end=" ", flush=True)

        try:
            result = None
            for attempt in range(3):
                try:
                    result = score_occupation_mistral(client, text)
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < 2:
                        wait = (attempt + 1) * 10
                        print(f"429, attente {wait}s...", end=" ", flush=True)
                        time.sleep(wait)
                    else:
                        raise

            if result:
                scores[code] = {
                    "code_pcs": code,
                    "title": title,
                    **result,
                }
                print(f"exposure={result['exposure']}")
        except Exception as e:
            print(f"ERREUR: {e}")
            errors.append(code)

        # Checkpoint incremental
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(list(scores.values()), f, ensure_ascii=False, indent=2)

        if i < len(to_score) - 1:
            time.sleep(args.delay)

    client.close()

    print(f"\nTermine. {len(scores)} professions scorees, {len(errors)} erreurs.")
    if errors:
        print(f"Erreurs : {errors[:10]}")

    # Stats finales
    vals = [s for s in scores.values() if "exposure" in s]
    if vals:
        avg = sum(s["exposure"] for s in vals) / len(vals)
        dist: dict[int, int] = {}
        for s in vals:
            b = s["exposure"]
            dist[b] = dist.get(b, 0) + 1

        print(f"\nExposition IA moyenne : {avg:.1f}/10 ({len(vals)} professions)")
        print("Distribution:")
        for k in sorted(dist):
            bar = "\u2588" * dist[k]
            print(f"  {k:2d}: {bar[:50]} ({dist[k]})")


if __name__ == "__main__":
    main()
