"""Pipeline complet : prend un lead du CSV, produit son site HTML.

Etapes :
1. scrape_riche : re-scrape Insta + telecharge 12-30 photos en local
2. photo_curator : Claude Vision selectionne les 9 meilleures
3. brand_and_copy : Claude Sonnet genere palette + ton + copy personnalisee
4. site_builder : assemble tout via Jinja2 -> index.html

Cout total par site : ~$0.11
- Apify scrape : $0.07
- Claude Vision : $0.02
- Claude Sonnet : $0.025

Usage:
    # Depuis un CSV de leads (insta_first_finder.py) :
    python generate_site.py --csv output/leads_estheticienne_bordeaux.csv

    # Pour un seul handle :
    python generate_site.py --handle institut_beauty_bar --metier "esthéticienne" --ville "Bordeaux"

    # Limiter aux N premiers leads :
    python generate_site.py --csv output/leads_estheticienne_bordeaux.csv --limit 3
"""

import argparse
import csv
import sys
import time
from pathlib import Path

from brand_and_copy import genere_brand_et_copy
from copy_reviewer import revise_copy
from google_reviews import scrape_pour_lead as scrape_avis_pour_lead
from photo_curator import cure_photos
from scrape_riche import scrape_complet, slugifie
from site_builder import construit_site


def genere_un_site(handle: str, metier: str, ville: str, dossier_base: Path,
                   max_posts: int = 30, max_galerie: int = 9) -> Path | None:
    """Pipeline complet pour 1 lead. Renvoie le chemin de l'index.html ou None."""
    slug = slugifie(handle)
    dossier = dossier_base / slug
    dossier.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {handle} ({metier} {ville}) ===")
    t0 = time.time()

    # 1. Scrape
    if (dossier / "metadata.json").exists():
        print("  [skip] metadata.json deja present, on reutilise")
    else:
        if not scrape_complet(handle, dossier, max_posts):
            print(f"  [ECHEC] scrape rate pour @{handle}")
            return None

    # 2. Curation photos
    if (dossier / "photo_selection.json").exists():
        print("  [skip] photo_selection.json deja present, on reutilise")
    else:
        if not cure_photos(dossier, metier, max_galerie):
            print(f"  [ECHEC] curation photos ratee pour @{handle}")
            return None

    # 3. Brand + copy (1ere passe Opus)
    if (dossier / "brand_and_copy.json").exists():
        print("  [skip] brand_and_copy.json deja present, on reutilise")
    else:
        if not genere_brand_et_copy(dossier, metier, ville):
            print(f"  [ECHEC] generation brand+copy ratee pour @{handle}")
            return None
        # 3 bis. Revision editoriale Opus (sauf si deja revisee)
        if not (dossier / "brand_and_copy_avant_revision.json").exists():
            try:
                revise_copy(dossier)
            except Exception as e:
                print(f"  [warn] revision copy echouee : {e}")

    # 4. Avis Google (optionnel : ne bloque pas si echec)
    if (dossier / "google_reviews.json").exists():
        print("  [skip] google_reviews.json deja present, on reutilise")
    else:
        try:
            scrape_avis_pour_lead(dossier, ville, max_avis=6)
        except Exception as e:
            print(f"  [warn] scrape avis Google echoue : {e}")

    # 5. Build HTML
    chemin = construit_site(dossier)
    if not chemin:
        print(f"  [ECHEC] build HTML rate pour @{handle}")
        return None

    duree = time.time() - t0
    print(f"  [OK] site genere en {duree:.0f}s -> {chemin}")
    return chemin


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline complet de generation de sites preview.")
    parser.add_argument("--csv", help="CSV de leads (sortie de insta_first_finder.py)")
    parser.add_argument("--handle", help="Pour traiter un seul handle (sans --csv)")
    parser.add_argument("--metier", help="Metier (requis avec --handle)")
    parser.add_argument("--ville", help="Ville (requis avec --handle)")
    parser.add_argument("--limit", type=int, default=0, help="Limite de leads (0 = tous)")
    parser.add_argument("--output", default="output/sites", help="Dossier de sortie")
    parser.add_argument("--max-posts", type=int, default=30, help="Posts a scraper (defaut 30)")
    parser.add_argument("--max-galerie", type=int, default=9, help="Photos galerie max (defaut 9)")
    args = parser.parse_args()

    dossier_base = Path(args.output)
    dossier_base.mkdir(parents=True, exist_ok=True)

    if args.handle:
        if not args.metier or not args.ville:
            print("--metier et --ville requis avec --handle", file=sys.stderr)
            return 1
        chemin = genere_un_site(args.handle.lstrip("@"), args.metier, args.ville, dossier_base,
                                args.max_posts, args.max_galerie)
        return 0 if chemin else 1

    if not args.csv:
        print("Fournir --csv OU --handle. python generate_site.py --help", file=sys.stderr)
        return 1

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV introuvable : {csv_path}", file=sys.stderr)
        return 1

    with csv_path.open(encoding="utf-8") as f:
        leads = list(csv.DictReader(f))
    if args.limit:
        leads = leads[: args.limit]

    print(f"Generation pour {len(leads)} lead(s).")
    reussis = 0
    for i, ld in enumerate(leads, 1):
        print(f"\n[{i}/{len(leads)}]", end="")
        chemin = genere_un_site(
            ld["handle"],
            ld.get("metier", ""),
            ld.get("ville", ""),
            dossier_base,
            args.max_posts,
            args.max_galerie,
        )
        if chemin:
            reussis += 1

    print(f"\n=== Termine : {reussis}/{len(leads)} sites generes ===")
    print(f"Sites disponibles dans : {dossier_base}/")
    return 0 if reussis else 1


if __name__ == "__main__":
    sys.exit(main())
