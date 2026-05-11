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
    return f"""Tu es un directeur artistique specialise dans le webdesign pour
commercants locaux. Tu analyses des photos Instagram d'un commerce ({metier})
pour selectionner les meilleures pour la galerie de son futur site web.

Pour chaque photo, tu evalues :
1. Sa categorie parmi : {", ".join(CATEGORIES)}
2. Son score de pertinence sur 10 pour un site pro de ce metier :
   - 9-10 : photo parfaite pour le site (resultat client net, ambiance lieu pro)
   - 6-8 : bonne photo, montre le savoir-faire
   - 3-5 : moyenne, utilisable seulement si pas mieux
   - 0-2 : ne pas mettre sur le site (selfie perso, meme, texte uniquement)
3. Une description courte (max 80 caracteres)
4. Si elle doit etre dans la galerie finale (max 9 photos)

Tu privilegies pour la galerie finale :
- Variete de categories (eviter 9x la meme chose)
- resultat_client et ambiance_lieu en priorite
- Eviter selfie_perso, texte_promo, meme_humour
- Photos professionnelles, bien cadrees, bonne lumiere

Tu reponds UNIQUEMENT en JSON valide selon ce format strict :
{{
  "photos": [
    {{"fichier": "post_001.jpg", "categorie": "resultat_client",
      "score": 9, "description": "Gros plan manucure rose poudre, lumiere studio",
      "selection_galerie": true}}
  ],
  "ordre_galerie": ["post_001.jpg", "post_003.jpg", ...],
  "synthese": "Description en 1-2 phrases du contenu Insta et de la qualite visuelle"
}}

L'ordre_galerie contient max 9 fichiers tries du meilleur au moins bon.
"""


def cure_photos(dossier_site: Path, metier: str, max_galerie: int = 9) -> dict | None:
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
