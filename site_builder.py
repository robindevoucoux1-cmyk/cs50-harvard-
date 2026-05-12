"""Assemble brand_and_copy.json + photo_selection.json + metadata.json
en un site HTML statique deployable.

Le template Jinja2 utilise les CSS variables pour appliquer la palette
specifique a chaque marque + injecte les Google Fonts choisies.

Sortie : output/sites/<slug>/index.html + assets/ (deja la)
"""

import datetime
import json
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

DOSSIER_TEMPLATES = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(DOSSIER_TEMPLATES)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def construit_site(dossier_site: Path) -> Path | None:
    """Charge les artefacts et genere index.html dans dossier_site."""
    meta_path = dossier_site / "metadata.json"
    sel_path = dossier_site / "photo_selection.json"
    brief_path = dossier_site / "brand_and_copy.json"

    for p in (meta_path, sel_path, brief_path):
        if not p.exists():
            print(f"  [builder-error] manque {p.name}")
            return None

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    selection = json.loads(sel_path.read_text(encoding="utf-8"))
    brief = json.loads(brief_path.read_text(encoding="utf-8"))

    # google_reviews est optionnel
    avis = None
    avis_path = dossier_site / "google_reviews.json"
    if avis_path.exists():
        a = json.loads(avis_path.read_text(encoding="utf-8"))
        if a.get("trouve"):
            avis = a

    # Construit la galerie ordonnee avec descriptions
    photos_dict = {p["fichier"]: p for p in selection.get("photos", [])}
    posts_dict = {p["fichier"].replace("assets/", ""): p for p in metadata.get("posts", [])}
    galerie = []
    for fichier in selection.get("ordre_galerie", []):
        info = photos_dict.get(fichier, {})
        galerie.append({
            "fichier_local": fichier,
            "categorie": info.get("categorie", ""),
            "description": info.get("description", ""),
            "url_post": posts_dict.get(fichier, {}).get("url_post", ""),
        })

    if not galerie:
        print("  [builder-error] galerie vide, impossible de generer le site")
        return None

    # Choix du lien de booking (externalUrl si c'est un Planity/Treatwell/etc., sinon Insta)
    booking_url = metadata.get("externalUrl") or f"https://www.instagram.com/{metadata.get('handle','')}/"

    # nom commercial : priorite absolue au nom Google Maps officiel s'il existe
    # (= vraie raison sociale du business), sinon brief.nom_commercial (Claude),
    # sinon fullName Insta, sinon handle.
    nom_commercial = (
        (avis.get("nom_fiche") if avis else None)
        or brief.get("nom_commercial")
        or metadata.get("fullName")
        or f"@{metadata.get('handle','')}"
    )
    contexte = {
        "brand": {
            "fullName": nom_commercial,
            "handle": metadata.get("handle", ""),
            "categorie": metadata.get("businessCategoryName", ""),
            "url_instagram": metadata.get("url_profil") or f"https://www.instagram.com/{metadata.get('handle','')}/",
            "argument_unique": brief.get("brand_voice", {}).get("argument_unique", ""),
            "voix": brief.get("brand_voice", {}),
            "sous_metier": brief.get("sous_metier_detecte", ""),
            "soncas": brief.get("soncas_dominants", []),
        },
        "palette": brief.get("palette", {}),
        "typo": brief.get("typographie", {}),
        "copy": brief.get("copy", {}),
        "meta": brief.get("meta", {}),
        "galerie": galerie,
        "booking_url": booking_url,
        "avis": avis,
        "annee": datetime.datetime.now().year,
    }

    env = _env()
    template = env.get_template("site.html.j2")
    html = template.render(**contexte)

    chemin = dossier_site / "index.html"
    chemin.write_text(html, encoding="utf-8")
    print(f"  [builder] site genere : {chemin}")
    print(f"  [builder] palette : {brief['palette'].get('primaire','?')} / {brief['palette'].get('secondaire','?')}")
    print(f"  [builder] photos galerie : {len(galerie)}")
    return chemin


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python site_builder.py <dossier_site>")
        return 1
    chemin = construit_site(Path(sys.argv[1]))
    return 0 if chemin else 1


if __name__ == "__main__":
    sys.exit(main())
