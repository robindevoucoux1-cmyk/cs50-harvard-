"""Enrichit un CSV de prospects avec leur Instagram (handle, bio, photos).

Pipeline pour chaque ligne :
1. cherche le handle Insta via DuckDuckGo (nom + ville)
2. si trouve, scrape le profil (bio, photos, posts)
3. ajoute les donnees au prospect
4. ecrit prospect_<nom>.json par prospect + prospects_enriched.csv

Usage:
    python prospect_enricher.py --input output/prospects.csv
    python prospect_enricher.py --input output/test_bordeaux.csv --limit 10
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from insta_finder import cherche_handle
from insta_scraper import InstaScraper, profil_to_dict


def slugifie(s: str) -> str:
    autorise = "abcdefghijklmnopqrstuvwxyz0123456789-"
    s = s.lower().replace(" ", "-").replace("'", "")
    return "".join(c for c in s if c in autorise)[:60] or "prospect"


def enrichi_un(prospect: dict, scraper: InstaScraper, dossier_profils: Path) -> dict:
    """Enrichit un prospect avec Insta. Mute et renvoie le dict."""
    nom = prospect.get("nom", "")
    ville = prospect.get("ville", "")
    print(f"  -> {nom} ({ville})")

    handle = cherche_handle(nom, ville)
    prospect["insta_handle"] = handle or ""
    if not handle:
        print("    pas d'Insta trouve")
        return prospect

    print(f"    @{handle} - scrape...")
    profil = scraper.scrape_profil(handle, max_posts=6)
    if not profil:
        print("    profil bloque/inexistant")
        return prospect

    prospect["insta_followers"] = profil.nb_followers
    prospect["insta_bio"] = profil.bio.replace("\n", " ")[:300]
    prospect["insta_site_web"] = profil.site_web
    prospect["insta_nb_posts"] = profil.nb_posts
    prospect["insta_categorie"] = profil.categorie

    chemin = dossier_profils / f"{slugifie(nom)}.json"
    chemin.write_text(
        json.dumps(profil_to_dict(profil), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"    profil sauve dans {chemin.name} ({profil.nb_followers} followers, {len(profil.posts)} posts)")
    return prospect


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrichit un CSV de prospects avec leur Insta.")
    parser.add_argument("--input", required=True, help="CSV produit par lead_finder.py")
    parser.add_argument("--output", default=None, help="CSV enrichi (defaut: <input>_enriched.csv)")
    parser.add_argument("--limit", type=int, default=0, help="Limite de prospects a traiter (0 = tous)")
    parser.add_argument("--delai", type=float, default=20.0, help="Delai entre 2 prospects (secondes)")
    args = parser.parse_args()

    chemin_in = Path(args.input)
    if not chemin_in.exists():
        print(f"Fichier introuvable : {chemin_in}", file=sys.stderr)
        return 1

    chemin_out = Path(args.output) if args.output else chemin_in.with_name(chemin_in.stem + "_enriched.csv")
    dossier_profils = chemin_out.parent / "profils"
    dossier_profils.mkdir(parents=True, exist_ok=True)

    with chemin_in.open(encoding="utf-8") as f:
        prospects = list(csv.DictReader(f))

    if args.limit:
        prospects = prospects[: args.limit]

    print(f"Enrichissement de {len(prospects)} prospects (delai {args.delai}s entre chaque)\n")
    scraper = InstaScraper(delai_entre_requetes=args.delai)

    enrichis = []
    for i, p in enumerate(prospects, 1):
        print(f"[{i}/{len(prospects)}]")
        enrichis.append(enrichi_un(p, scraper, dossier_profils))
        if i < len(prospects):
            time.sleep(args.delai)

    champs = list({k for p in enrichis for k in p.keys()})
    with chemin_out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=champs)
        writer.writeheader()
        writer.writerows(enrichis)

    avec_insta = sum(1 for p in enrichis if p.get("insta_handle"))
    print(f"\nTermine : {avec_insta}/{len(enrichis)} prospects avec Insta trouve")
    print(f"CSV enrichi : {chemin_out}")
    print(f"Profils JSON : {dossier_profils}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
