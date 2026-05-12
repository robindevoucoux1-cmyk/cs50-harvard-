"""Passe de revision editoriale : un 2e Opus relit la copy generee et la
ameliore en mode redacteur en chef magazine.

Strategie : on prend le brand_and_copy.json existant, on l'envoie a Opus
avec un prompt severe de redaction en chef. Opus identifie les tics IA,
les phrases plates, les fautes residuelles, et reecrit le tout en
preservant la structure et les faits.

Cout estime : ~$0.15 par site (Opus 4.7).
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]

MODELE_REVIEWER = "claude-opus-4-7"


PROMPT_REVISEUR = """Tu es redacteur en chef d'un magazine francais haut de
gamme (Le Monde Style, M le magazine, Numero, Vogue France). Tu reprends une
copy de site web ecrite par un junior. Tu la relis comme un correcteur de
maison d'edition : chaque phrase doit etre tenue, le rythme doit respirer,
le vocabulaire doit etre choisi. Aucune approximation.

Tu vas recevoir un brief complet (palette, services, h1, tagline, FAQ, etc.).
Tu retournes EXACTEMENT la meme structure JSON, mais avec une copy reecrite
au niveau magazine.

REGLES STRICTES DE REVISION :

1. TRAQUE ET ELIMINE LES TICS IA :
   "Forte de", "Veritable expertise", "Une experience unique", "Au coeur de",
   "Un univers", "Un ecrin", "Plonger dans", "Sublimer", "Magnifier", "Reveler",
   "Sur-mesure" en par-defaut, "Excellence" en titre, "Une touche de", "Pour
   une experience", "L'art de", "Le pouvoir des", "L'eclat de", "Boost",
   "Cocon" sans raison, "Inedit", "Une parenthese", "L'alliance subtile",
   "Une signature", "Le geste juste", "Maitre" / "Maitresse", "Plus qu'un
   X, un Y", "Et si vous + Y", "Bienvenue dans", "Faire rayonner".
   Si tu en trouves, REECRIS la phrase entierement.

2. CORRIGE L'ORTHOGRAPHE ET LA GRAMMAIRE :
   - Accents (e, e, e, a, u) corrects partout
   - Accords sujet-verbe et participes passes parfaits
   - Apostrophes typographiques ' (U+2019)
   - Pas de tirets cadratins (-) ni demi-cadratins (-)
   - Pas de fautes de frappe

3. AMELIORE LE STYLE :
   - Phrases courtes ou moyennes, jamais lourdes. Alterne le rythme.
   - Une idee par phrase. Pas de phrases qui empilent 3 propositions.
   - Actif plutot que passif ("je vous accueille" pas "vous etes accueilli").
   - Concret plutot que generique. Si le service est "Soin visage Kobido",
     dis quelque chose de specifique au Kobido, pas du blabla generique.
   - Sensoriel quand approprie : un toucher, une lumiere, un geste.

4. VERIFIE LA COHERENCE :
   - Vouvoiement ou tutoiement UNIFORME dans toute la copy (jamais melange).
   - Le ton du H1 doit correspondre au ton de l'about, des services et de la FAQ.
   - Le nom_commercial doit etre utilise tel quel quand on parle du salon.

5. NE JAMAIS INVENTER :
   - Ne rajoute aucun chiffre, certification, annee d'experience, distinction
     qui ne serait pas dans le brief original.
   - Si le junior n'a pas mis de prix, ne mets pas de prix.
   - Si tu doutes d'une info, retire-la.

EXEMPLE DE TRANSFORMATION :

Avant (junior IA) :
"H1 : Sublimez votre peau avec une experience unique au coeur de Bordeaux."
"Tagline : Forte de mon experience, je vous propose un veritable ecrin de
beaute pour magnifier votre regard."

Apres (toi, redacteur) :
"H1 : Une peau qui respire, vraiment."
"Tagline : Diagnostic d'abord, soin ensuite. A Bordeaux, sur rendez-vous."

FORMAT DE REPONSE : exactement la meme structure JSON que l'input, avec la
copy reecrite. Garde tous les champs (palette, typographie, photo_index,
brand_voice, etc.) inchanges. Modifie SEULEMENT les champs textuels qui
en ont besoin :
- nom_commercial (si tics IA detectes)
- copy.h1, copy.tagline, copy.about_titre, copy.about_texte
- copy.services_titre + chaque services[].nom, services[].description
- copy.raisons_titre + chaque raisons[].titre, raisons[].texte
- copy.galerie_titre
- chaque copy.faq[].question, copy.faq[].reponse
- copy.cta_principal, copy.cta_secondaire
- copy.footer_tagline
- meta.title, meta.description

Reponds UNIQUEMENT le JSON, rien autour.
"""


def _enleve_tirets(s):
    if not isinstance(s, str):
        return s
    s = s.replace(" — ", ", ").replace(" – ", ", ")
    s = s.replace("—", ",").replace("–", ",")
    while ", ," in s or ",," in s:
        s = s.replace(",,", ",").replace(", ,", ",")
    return s.strip()


def _walk_clean(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                node[k] = _enleve_tirets(v)
            else:
                _walk_clean(v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                node[i] = _enleve_tirets(v)
            else:
                _walk_clean(v)


def revise_copy(dossier_site: Path) -> dict | None:
    """Charge brand_and_copy.json, le revise via Opus, sauve la version reecrite."""
    brief_path = dossier_site / "brand_and_copy.json"
    if not brief_path.exists():
        print(f"  [reviewer-error] brand_and_copy.json absent dans {dossier_site}")
        return None

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    # Sauvegarde du brief V1 avant revision
    raw_path = dossier_site / "brand_and_copy_avant_revision.json"
    raw_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")

    if anthropic is None:
        raise RuntimeError("anthropic non installe.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY manquant.")

    client = anthropic.Anthropic()
    # On retire _meta du brief avant envoi pour ne pas le voir comme du texte a reviser
    brief_envoye = {k: v for k, v in brief.items() if not k.startswith("_")}

    print(f"  [reviewer] revision editoriale via {MODELE_REVIEWER}...")
    resp = client.messages.create(
        model=MODELE_REVIEWER,
        max_tokens=8192,
        system=PROMPT_REVISEUR,
        messages=[{"role": "user", "content": "Voici le brief a reviser :\n\n" + json.dumps(brief_envoye, ensure_ascii=False, indent=2)}],
    )

    texte = resp.content[0].text.strip()
    if "```" in texte:
        texte = texte.split("```json", 1)[-1].split("```", 1)[0].strip() if "```json" in texte \
            else texte.split("```", 1)[-1].split("```", 1)[0].strip()

    try:
        brief_revise = json.loads(texte)
    except json.JSONDecodeError as e:
        print(f"  [reviewer-error] JSON parse fail : {e}")
        print(f"  Reponse brute : {texte[:1000]}")
        return None

    # Post-process : tirets cadratins
    _walk_clean(brief_revise)

    # Cout Opus 4.7
    cout = (resp.usage.input_tokens / 1_000_000 * 15.0) + (resp.usage.output_tokens / 1_000_000 * 75.0)
    brief_revise["_meta"] = {
        "modele_revision": resp.model,
        "input_tokens_revision": resp.usage.input_tokens,
        "output_tokens_revision": resp.usage.output_tokens,
        "cout_revision_usd": round(cout, 4),
        **brief.get("_meta", {}),
    }

    brief_path.write_text(json.dumps(brief_revise, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [reviewer] copy revisee. cout : ~${cout:.3f}")

    # Diff sommaire
    print(f"  [reviewer] avant -> apres :")
    avant_h1 = brief.get("copy", {}).get("h1", "")
    apres_h1 = brief_revise.get("copy", {}).get("h1", "")
    if avant_h1 != apres_h1:
        print(f"    H1     : {avant_h1!r}")
        print(f"          -> {apres_h1!r}")
    avant_tag = brief.get("copy", {}).get("tagline", "")
    apres_tag = brief_revise.get("copy", {}).get("tagline", "")
    if avant_tag != apres_tag:
        print(f"    Tag    : {avant_tag!r}")
        print(f"          -> {apres_tag!r}")
    avant_nom = brief.get("nom_commercial", "")
    apres_nom = brief_revise.get("nom_commercial", "")
    if avant_nom != apres_nom:
        print(f"    Nom    : {avant_nom!r} -> {apres_nom!r}")

    return brief_revise


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python copy_reviewer.py <dossier_site>")
        return 1
    return 0 if revise_copy(Path(sys.argv[1])) else 1


if __name__ == "__main__":
    sys.exit(main())
