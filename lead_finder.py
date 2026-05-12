"""Trouve des commerces SANS site web via OpenStreetMap (Overpass API).

Usage:
    python lead_finder.py
    python lead_finder.py --ville Lyon --metier osteopathe
    python lead_finder.py --output prospects_lyon.csv

Gratuit, sans cle API, sans carte bancaire.
"""

import argparse
import csv
import sys
import time
import unicodedata
from pathlib import Path

import requests

from config import VILLES, METIERS

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "lead-finder/1.0 (prospection commerciale, contact via github)"}

METIER_TO_OSM = {
    # Beaute / bien-etre
    "esthéticienne": [("shop", "beauty")],
    "salon de beauté": [("shop", "beauty")],
    "institut de beauté": [("shop", "beauty")],
    "spa": [("leisure", "spa"), ("shop", "beauty")],
    "onglerie": [("shop", "beauty"), ("shop", "nail_salon")],
    "barbier": [("shop", "hairdresser")],
    "coiffeur": [("shop", "hairdresser")],
    "tatoueur": [("shop", "tattoo")],
    # Sante / medical
    "ostéopathe": [("healthcare", "alternative"), ("healthcare:speciality", "osteopathy")],
    "kinésithérapeute": [("healthcare", "physiotherapist")],
    "dentiste": [("amenity", "dentist")],
    "psychologue": [("healthcare", "psychotherapist")],
    "psychothérapeute": [("healthcare", "psychotherapist")],
    "naturopathe": [("healthcare", "alternative")],
    "sophrologue": [("healthcare", "alternative"), ("healthcare:speciality", "sophrology")],
    "diététicien": [("healthcare", "dietitian")],
    "podologue": [("healthcare", "podiatrist")],
    "orthophoniste": [("healthcare", "speech_therapist")],
    "sage-femme": [("healthcare", "midwife")],
    "médecin": [("healthcare", "doctor"), ("amenity", "doctors")],
    "pharmacie": [("amenity", "pharmacy")],
    "vétérinaire": [("amenity", "veterinary")],
    # Sport / fitness
    "coach sportif": [("leisure", "fitness_centre"), ("sport", "fitness")],
    "salle de sport": [("leisure", "fitness_centre")],
    "yoga studio": [("sport", "yoga"), ("leisure", "fitness_centre")],
    "pilates": [("sport", "pilates"), ("leisure", "fitness_centre")],
    "boxe": [("sport", "boxing"), ("leisure", "fitness_centre")],
    "crossfit": [("sport", "crossfit"), ("leisure", "fitness_centre")],
    # Restauration
    "restaurant": [("amenity", "restaurant"), ("amenity", "fast_food"), ("amenity", "cafe")],
    "café": [("amenity", "cafe")],
    "bar": [("amenity", "bar"), ("amenity", "pub")],
    "boulangerie": [("shop", "bakery")],
    "boulangerie artisanale": [("shop", "bakery")],
    "pâtisserie": [("shop", "pastry")],
    "chocolaterie": [("shop", "chocolate")],
    "fromager": [("shop", "cheese")],
    "boucher": [("shop", "butcher")],
    "caviste": [("shop", "wine"), ("shop", "alcohol")],
    "traiteur": [("shop", "deli"), ("craft", "caterer")],
    "glacier": [("amenity", "ice_cream"), ("shop", "ice_cream")],
    # Mode / shopping
    "boutique de vêtements": [("shop", "clothes")],
    "bijoutier": [("shop", "jewelry")],
    "opticien": [("shop", "optician")],
    "chausseur": [("shop", "shoes")],
    "fleuriste": [("shop", "florist")],
    "librairie": [("shop", "books")],
    # Creation / artisanat
    "photographe": [("craft", "photographer"), ("shop", "photo")],
    "couturier": [("craft", "tailor")],
    "menuisier": [("craft", "carpenter")],
    "ébéniste": [("craft", "cabinet_maker")],
    "cordonnier": [("craft", "shoemaker")],
    # Maison / batiment
    "plombier": [("craft", "plumber")],
    "électricien": [("craft", "electrician")],
    "peintre": [("craft", "painter")],
    "carreleur": [("craft", "tiler")],
    "couvreur": [("craft", "roofer")],
    "maçon": [("craft", "stonemason")],
    "jardinier": [("craft", "gardener")],
    "paysagiste": [("craft", "gardener")],
    # Services / bureaux
    "architecte": [("office", "architect")],
    "architecte d'intérieur": [("office", "architect")],
    "avocat": [("office", "lawyer")],
    "notaire": [("office", "notary")],
    "comptable": [("office", "accountant")],
    "agence immobilière": [("office", "estate_agent")],
    "auto-école": [("amenity", "driving_school")],
    "agence de voyage": [("shop", "travel_agency")],
    "garagiste": [("shop", "car_repair"), ("amenity", "car_repair")],
}


def normalise(s: str) -> str:
    """Enleve accents et passe en minuscules pour matcher metiers/villes."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def resoud_metier(saisi: str) -> tuple[str, list[tuple[str, str]]] | tuple[None, None]:
    """Retrouve le metier officiel a partir d'une saisie (avec ou sans accents)."""
    cible = normalise(saisi)
    for officiel, tags in METIER_TO_OSM.items():
        if normalise(officiel) == cible:
            return officiel, tags
    return None, None


def construit_requete(ville: str, tags: list[tuple[str, str]]) -> str:
    """Genere une requete Overpass QL pour une ville et des tags OSM."""
    filtres = "".join(f'node["{k}"="{v}"](area.searchArea);' for k, v in tags)
    return f"""
    [out:json][timeout:60];
    area["name"="{ville}"]["boundary"="administrative"]->.searchArea;
    (
      {filtres}
    );
    out body;
    """


def interroge_overpass(requete: str, tentatives: int = 3) -> list[dict]:
    """Envoie la requete a Overpass avec retry exponentiel."""
    delai = 5
    for tentative in range(tentatives):
        try:
            r = requests.post(OVERPASS_URL, data={"data": requete}, headers=HEADERS, timeout=90)
            r.raise_for_status()
            return r.json().get("elements", [])
        except requests.RequestException as e:
            if tentative == tentatives - 1:
                print(f"  Echec apres {tentatives} tentatives: {e}", file=sys.stderr)
                return []
            print(f"  Erreur ({e}), retry dans {delai}s...", file=sys.stderr)
            time.sleep(delai)
            delai *= 2
    return []


def a_un_site_web(tags: dict) -> bool:
    """Detecte si le commerce a deja un site (on veut l'EXCLURE)."""
    cles_site = ["website", "contact:website", "url", "contact:url"]
    return any(tags.get(k) for k in cles_site)


def extrait_prospect(element: dict, ville: str, metier: str) -> dict | None:
    """Transforme un element OSM en ligne de prospect, ou None si pas pertinent."""
    tags = element.get("tags", {})
    nom = tags.get("name")
    if not nom:
        return None
    if a_un_site_web(tags):
        return None

    telephone = tags.get("phone") or tags.get("contact:phone") or ""
    adresse_parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:postcode", ""),
        tags.get("addr:city", ville),
    ]
    adresse = " ".join(p for p in adresse_parts if p).strip()

    lat = element.get("lat", "")
    lon = element.get("lon", "")
    lien_maps = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if lat else ""
    lien_recherche_insta = f"https://www.instagram.com/explore/tags/{nom.lower().replace(' ', '')}/"

    return {
        "nom": nom,
        "metier": metier,
        "ville": ville,
        "telephone": telephone,
        "email": tags.get("contact:email") or tags.get("email", ""),
        "adresse": adresse,
        "facebook": tags.get("contact:facebook") or tags.get("facebook", ""),
        "instagram": tags.get("contact:instagram") or tags.get("instagram", ""),
        "lien_maps": lien_maps,
        "recherche_insta": lien_recherche_insta,
    }


def cherche_prospects(villes: list[str], metiers: list[str]) -> list[dict]:
    """Boucle principale sur villes x metiers."""
    prospects = []
    vus = set()

    for ville in villes:
        for metier_saisi in metiers:
            metier, tags_osm = resoud_metier(metier_saisi)
            if not tags_osm:
                print(f"  [skip] Pas de mapping OSM pour '{metier_saisi}'")
                continue

            print(f"-> {metier} a {ville}...", end=" ", flush=True)
            requete = construit_requete(ville, tags_osm)
            elements = interroge_overpass(requete)

            nouveaux = 0
            for el in elements:
                prospect = extrait_prospect(el, ville, metier)
                if not prospect:
                    continue
                cle = (prospect["nom"], prospect["ville"])
                if cle in vus:
                    continue
                vus.add(cle)
                prospects.append(prospect)
                nouveaux += 1

            print(f"{nouveaux} prospects sans site")
            time.sleep(1)

    return prospects


def ecrit_csv(prospects: list[dict], chemin: Path) -> None:
    if not prospects:
        print("Aucun prospect a ecrire.")
        return
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(prospects[0].keys()))
        writer.writeheader()
        writer.writerows(prospects)
    print(f"\n{len(prospects)} prospects ecrits dans {chemin}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Trouve des commerces sans site web via OSM.")
    parser.add_argument("--ville", help="Une seule ville (sinon toutes celles de config.py)")
    parser.add_argument("--metier", help="Un seul metier (sinon tous ceux de config.py)")
    parser.add_argument("--output", default="output/prospects.csv", help="Chemin du CSV de sortie")
    args = parser.parse_args()

    villes = [args.ville] if args.ville else VILLES
    metiers = [args.metier] if args.metier else METIERS

    print(f"Recherche : {len(villes)} ville(s) x {len(metiers)} metier(s)\n")
    prospects = cherche_prospects(villes, metiers)
    ecrit_csv(prospects, Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
