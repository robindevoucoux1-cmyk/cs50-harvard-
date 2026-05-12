"""Selection intelligente des photos Instagram pour la galerie d'un site.

Utilise Claude Haiku 4.5 (vision) pour analyser chaque photo telechargee
par scrape_riche.py et :
1. La classer (resultat_client, ambiance_lieu, produit, selfie_perso, etc.)
2. Lui donner un score de pertinence metier (0-10)
3. Selectionner les 9 meilleures pour la galerie du site

Strategie : un seul appel API avec toutes les images. Plus efficient.
Cout : ~$0.02 par lead (12-30 images analysees en batch).

Sortie : output/sites/<slug>/photo_selection.json
"""

import base64
import json
import os
import sys
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

load_dotenv()

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]

MODELE_VISION = "claude-haiku-4-5"
TAILLE_MAX = 1024  # px max sur le plus grand cote, pour limiter les tokens vision

CATEGORIES = [
    "resultat_client",   # avant/apres, resultat direct (ongles, peau, lash)
    "ambiance_lieu",     # interieur du salon, deco, vitrine
    "produit",           # produits utilises en mise en scene
    "portrait_pro",      # portrait professionnel de la praticienne
    "evenement",         # ouverture, journee portes ouvertes, salon
    "tutoriel",          # photos pedagogiques, schemas
    "selfie_perso",      # vie privee, hors contexte pro
    "texte_promo",       # image surtout texte (tarifs, annonces)
    "meme_humour",       # meme, blague, non pro
    "divers",
]


def _redimensionne(chemin: Path, taille_max: int = TAILLE_MAX) -> tuple[bytes, str]:
    """Charge une image, la redimensionne et la renvoie en bytes JPEG."""
    with Image.open(chemin) as img:
        img = img.convert("RGB")
        img.thumbnail((taille_max, taille_max), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue(), "image/jpeg"


def _client_anthropic():
    if anthropic is None:
        raise RuntimeError("anthropic non installe. pip install anthropic")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY manquant dans .env")
    return anthropic.Anthropic()


def _prompt_systeme(metier: str) -> str:
    return f"""Tu es un directeur artistique senior specialise dans le webdesign
pour commercants locaux ({metier}). Tu selectionnes les photos d'une marque
Instagram pour la galerie de son futur site web professionnel.

PRINCIPE FONDATEUR : MIEUX VAUT PEU DE TRES BONNES PHOTOS QUE BEAUCOUP DE
PHOTOS MOYENNES. Si tu n'as que 3 photos vraiment vendeuses, tu en gardes
3 et c'est tout. Le site n'est PAS un dump Instagram, c'est une vitrine
commerciale soignee.

REGLES STRICTES DE REJET (score 0-3, exclusion absolue) :
- FLACONS/TUBES/POTS DE PRODUITS POSES : photos de bouteilles, flacons, tubes
  de marque (DMK, Hydrafacial, Dermalogica, etc.) seuls ou alignes sur une
  table. Meme sur fond pro. Ca fait "photo de stock", pas vendeur.
  EXCEPTION : si le produit est en train d'etre applique sur la peau d'un
  client (geste pro visible), garder.
- PHOTOS MEDICALES BRUTES : peau rouge, irritee, acne severe, cortisone,
  apres-laser inflame visible. Effrayant pour le client.
- AVANT-APRES MAL CADRES : photos ou le "avant" prend la moitie sans
  l'apres visible, ou ou l'apres est mediocre.
- AMBIANCE HORS-SUJET : canapes vides, salle d'attente generique, decor
  non-distinctif, mur vide, reception banale. RIEN qui ne distingue le lieu.
- TEXTE PROMO : photos a 80%+ de texte (tarifs, annonces, dates).
- VIE PERSO : selfies maison, photos voyage, memes, humour, photos
  d'animaux, foule evenementielle.
- FLOUES / MAL ECLAIREES / MAL CADREES.

REGLES D'ACCEPTATION (score 7+) - tres exigeant :
- VRAIS RESULTATS CLIENTS NETS : manucure gros plan, cils macro, peau
  visiblement transformee, gros plan technique parfait.
- AVANT/APRES BIEN FAITS avec apres spectaculaire et lisible.
- PRATICIENNE AU TRAVAIL : geste pro visible (laser sur la peau, brush en
  main, instrument actif), client en cabine.
- LIEU AVEC CARACTERE : photo du cabinet avec un detail distinctif (decor,
  fauteuil signature, vitrine, atmosphere unique).
- PORTRAIT PRO de la praticienne dans son contexte de travail.

REGLES STRICTES D'ACCEPTATION (score 7+) :
- Resultats clients nets, bien cadres, bien eclaires (ex : manucure
  parfaite en gros plan, cils en macro, peau lisse en gros plan)
- Photos avant/apres clairement labellisees avec BEL apres
- Praticienne au travail dans son cabinet (geste pro visible)
- Cabinet/salon photographie avec ambiance et charme (pas juste un canape)
- Portrait pro de la praticienne avec materiel emblematique
- Detail technique : produit signature en main, instrument en action

CATEGORIES :
{", ".join(CATEGORIES)}

GALERIE FINALE : 3 a 6 photos MAXIMUM. Plus il y a de mauvaises photos
dans le pool original, plus tu en rejettes. Si tu n'as que 4 photos
qui meritent 7+/10, tu en gardes 4. Ne JAMAIS forcer a 6 si la qualite
n'est pas la.

DIVERSITE : evite 5 fois la meme categorie. Mix ideal : 3 resultats
clients + 1 ambiance lieu + 1 portrait pro + 1 technique en action.

REPONSE : JSON strict, rien d'autre :
{{
  "photos": [
    {{"fichier": "post_001.jpg", "categorie": "resultat_client",
      "score": 9, "description": "Description visuelle objective courte",
      "selection_galerie": true,
      "raison_rejet": "" }}
  ],
  "ordre_galerie": ["post_001.jpg", "post_003.jpg", ...],
  "synthese": "1-2 phrases sur la qualite visuelle du compte et le niveau de la selection"
}}

ordre_galerie : 3 a 6 fichiers tries du meilleur au moins bon.
raison_rejet : si selection_galerie = false, explique pourquoi en 1 phrase
courte (ex : "peau rouge irritee sans apres visible").
"""


def cure_photos(dossier_site: Path, metier: str, max_galerie: int = 6) -> dict | None:
    """Analyse toutes les photos d'un dossier site et selectionne les meilleures.

    Args:
        dossier_site: ex. output/sites/institut-beauty-bar/
        metier: ex. "esthéticienne"
        max_galerie: nombre max de photos dans la galerie finale

    Renvoie le dict de selection (et le sauve dans photo_selection.json).
    """
    assets = dossier_site / "assets"
    photos = sorted(assets.glob("post_*.jpg"))
    if not photos:
        print(f"  [curator] Aucune photo dans {assets}")
        return None

    print(f"  [curator] Analyse de {len(photos)} photos via Claude Vision...")
    client = _client_anthropic()

    content = [{"type": "text", "text": f"Voici les {len(photos)} photos a analyser. Reponds en JSON strict."}]
    for p in photos:
        img_bytes, media_type = _redimensionne(p)
        b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
        content.append({"type": "text", "text": f"Photo : {p.name}"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        })

    resp = client.messages.create(
        model=MODELE_VISION,
        max_tokens=2048,
        system=_prompt_systeme(metier),
        messages=[{"role": "user", "content": content}],
    )

    texte = resp.content[0].text.strip()
    # Robustesse : extraire le JSON si Claude ajoute du texte autour
    if "```" in texte:
        texte = texte.split("```json", 1)[-1].split("```", 1)[0].strip() if "```json" in texte \
            else texte.split("```", 1)[-1].split("```", 1)[0].strip()

    try:
        selection = json.loads(texte)
    except json.JSONDecodeError as e:
        print(f"  [curator-error] JSON parse fail : {e}")
        print(f"  Reponse brute : {texte[:500]}")
        return None

    # Limite l'ordre_galerie au max demande
    selection["ordre_galerie"] = (selection.get("ordre_galerie") or [])[:max_galerie]

    cout_estime = (resp.usage.input_tokens / 1_000_000 * 1.0) + (resp.usage.output_tokens / 1_000_000 * 5.0)
    selection["_meta"] = {
        "modele": resp.model,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "cout_estime_usd": round(cout_estime, 4),
    }

    chemin_out = dossier_site / "photo_selection.json"
    chemin_out.write_text(json.dumps(selection, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  [curator] {len(selection.get('ordre_galerie', []))} photos selectionnees pour la galerie")
    print(f"  [curator] cout : ~${cout_estime:.3f} ({resp.usage.input_tokens} in + {resp.usage.output_tokens} out)")
    return selection


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python photo_curator.py <dossier_site> <metier>")
        print("ex:    python photo_curator.py output/sites/institut-beauty-bar 'esthéticienne'")
        return 1

    dossier = Path(sys.argv[1])
    metier = sys.argv[2]
    sel = cure_photos(dossier, metier)
    if not sel:
        return 1

    print(f"\nSynthese : {sel.get('synthese', '')}")
    print(f"\nGalerie finale ({len(sel.get('ordre_galerie', []))} photos) :")
    photos_dict = {p["fichier"]: p for p in sel.get("photos", [])}
    for fichier in sel.get("ordre_galerie", []):
        info = photos_dict.get(fichier, {})
        print(f"  {fichier:<20} [{info.get('categorie', '?'):<20}] {info.get('score', '?'):>2}/10  {info.get('description', '')}")

    print(f"\nPhotos rejetees :")
    rejetees = [p for p in sel.get("photos", []) if p["fichier"] not in sel.get("ordre_galerie", [])]
    for info in rejetees:
        print(f"  {info['fichier']:<20} [{info['categorie']:<20}] {info['score']:>2}/10  {info['description']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
