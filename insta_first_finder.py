"""Pipeline 'Insta-first' : trouve directement sur Instagram les commercants
qui investissent dans leur com mais n'ont pas de site web.

Cible : commercants locaux avec
- >= MIN_FOLLOWERS abonnes
- >= MIN_POSTS posts (compte actif)
- pas de vrai site web (ils ont Linktree/Planity/Treatwell au mieux)
- ville confirmee dans la bio/handle

Strategie : 1 appel Apify search par couple (metier, ville). Le search
renvoie deja followers, bio, externalUrl, categorie -> aucun scrape
secondaire necessaire. Cout : ~$0.0015 par resultat brut.

Usage:
    python insta_first_finder.py --metier "esthéticienne" --ville "Bordeaux"
    python insta_first_finder.py --metier "coach sportif" --ville "Lyon" \\
        --min-followers 1000 --limit 50
"""

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from apify_scraper import _client

# Domaines a NE PAS considerer comme "vrai site web personnel".
# Si le seul externalUrl du compte pointe ici, le prospect reste qualifie.
DOMAINES_NON_SITE = {
    "planity.com", "www.planity.com",
    "treatwell.fr", "www.treatwell.fr", "treatwell.com",
    "linktr.ee", "www.linktr.ee",
    "linktree.com", "www.linktree.com",
    "beacons.ai", "beacons.page",
    "linkin.bio", "lnk.bio",
    "bio.link", "bento.me", "snipfeed.co",
    "campsite.bio", "msha.ke",
    "fresha.com", "www.fresha.com",
    "calendly.com",
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com",
    "tiktok.com", "www.tiktok.com",
    "youtube.com", "www.youtube.com",
    "wa.me", "api.whatsapp.com",
}

# Stopwords du metier qui n'apportent pas de signal
STOPWORDS_NOM = {"le", "la", "les", "de", "du", "des", "un", "une"}


def _normalise(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "".join(c if c.isalnum() else " " for c in s)


def _ville_dans(blob: str, ville: str) -> bool:
    return bool(ville) and _normalise(ville) in blob


def _metier_dans(blob: str, metier: str) -> bool:
    metier_norm = _normalise(metier)
    mots = [m for m in metier_norm.split() if len(m) >= 4 and m not in STOPWORDS_NOM]
    if any(m in blob for m in mots):
        return True
    synonymes = {
        "estheticienne": ["beaute", "beauty", "soin", "epilation", "manucure", "onglerie", "spa", "institut"],
        "sophrologue": ["sophro", "relaxation", "bien etre"],
        "naturopathe": ["naturo", "naturopathie"],
        "coach sportif": ["coaching", "fitness", "sport", "training", "personal trainer"],
        "yoga": ["yogi", "ashtanga", "vinyasa"],
    }
    for cle, syns in synonymes.items():
        if cle in metier_norm and any(s in blob for s in syns):
            return True
    return False


def _classifie_externalurl(url: str) -> str:
    """Retourne 'aucun', 'booking_ou_agregateur', ou 'vrai_site'."""
    if not url:
        return "aucun"
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return "vrai_site"
    if not host:
        return "aucun"
    if host in DOMAINES_NON_SITE:
        return "booking_ou_agregateur"
    if any(host.endswith("." + d) or host == d for d in DOMAINES_NON_SITE):
        return "booking_ou_agregateur"
    return "vrai_site"


def _extrait_contacts_bio(bio: str) -> tuple[str, str]:
    """Cherche un email et un telephone francais dans la bio."""
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", bio or "")
    email = email_match.group(0) if email_match else ""
    tel_match = re.search(r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}", bio or "")
    telephone = tel_match.group(0).strip() if tel_match else ""
    return email, telephone


def cherche_leads(metier: str, ville: str, limit: int = 30, min_followers: int = 500,
                  min_posts: int = 0, accepte_booking: bool = True) -> list[dict]:
    """Recherche les commercants Insta correspondant a metier+ville.

    Renvoie les leads bruts (1 appel Apify, ~$0.0015 * limit).
    Filtre applique : ville confirmee, metier coherent, followers OK,
    externalUrl absent ou agregateur (si accepte_booking=True).
    """
    client = _client()
    requete = re.sub(r"[!?.,:;\-+=*&%$#@/\\~^|<>()\[\]{}\"'`]+", " ", f"{metier} {ville}").strip()
    requete = re.sub(r"\s+", " ", requete)

    print(f"  Search Apify : {requete!r} (limit={limit})")
    run = client.actor("apify/instagram-search-scraper").call(run_input={
        "search": requete,
        "searchType": "user",
        "searchLimit": limit,
    })
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"  -> {len(items)} comptes brut(s)")

    qualifies = []
    for it in items:
        handle = (it.get("username") or "").strip().lower()
        if not handle:
            continue
        fol = it.get("followersCount") or 0
        bio = it.get("biography") or ""
        full = it.get("fullName") or ""
        ext_url = it.get("externalUrl") or ""
        categorie = it.get("businessCategoryName") or ""

        blob = _normalise(" ".join([handle, full, bio, categorie, ext_url]))
        signal_ville = _ville_dans(blob, ville)
        signal_metier = _metier_dans(blob, metier)
        type_site = _classifie_externalurl(ext_url)

        # filtre qualite
        if not signal_ville or not signal_metier:
            continue
        if fol < min_followers:
            continue
        if type_site == "vrai_site" and not accepte_booking:
            continue
        if type_site == "vrai_site":
            # accepte_booking=True mais site perso reel -> exclus quand meme
            # (l'utilisateur a deja un site, pas notre cible)
            continue

        email_bio, tel_bio = _extrait_contacts_bio(bio)
        qualifies.append({
            "nom": full or handle,
            "metier": metier,
            "ville": ville,
            "handle": handle,
            "url_profil": it.get("url") or f"https://www.instagram.com/{handle}/",
            "followers": fol,
            "follows": it.get("followsCount") or 0,
            "categorie": categorie,
            "bio": bio.replace("\n", " ")[:300],
            "external_url": ext_url,
            "type_external_url": type_site,
            "email_bio": email_bio,
            "telephone_bio": tel_bio,
            "is_business": it.get("isBusinessAccount", False),
            "verified": it.get("verified", False),
            "profil_pic": it.get("profilePicUrl") or "",
        })

    return qualifies


def main() -> int:
    parser = argparse.ArgumentParser(description="Trouve des commercants Insta sans site web.")
    parser.add_argument("--metier", required=True, help="ex: esthéticienne, coach sportif")
    parser.add_argument("--ville", required=True, help="ex: Bordeaux, Lyon")
    parser.add_argument("--limit", type=int, default=30, help="Resultats bruts max (default 30)")
    parser.add_argument("--min-followers", type=int, default=500)
    parser.add_argument("--min-posts", type=int, default=0)
    parser.add_argument("--output", default=None, help="CSV de sortie (defaut: output/leads_<metier>_<ville>.csv)")
    args = parser.parse_args()

    leads = cherche_leads(args.metier, args.ville, args.limit, args.min_followers, args.min_posts)

    print(f"\n{len(leads)} lead(s) qualifie(s) :")
    for ld in leads:
        signal = "📞" if ld["telephone_bio"] else "  "
        site = ld["type_external_url"]
        print(f"  {signal} @{ld['handle']:<35} {ld['followers']:>5} fol  [{site}]  {ld['bio'][:70]}")

    if leads:
        if args.output:
            chemin = Path(args.output)
        else:
            slug_m = re.sub(r"\W+", "_", args.metier.lower()).strip("_")
            slug_v = re.sub(r"\W+", "_", args.ville.lower()).strip("_")
            chemin = Path("output") / f"leads_{slug_m}_{slug_v}.csv"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=leads[0].keys())
            writer.writeheader()
            writer.writerows(leads)
        print(f"\nCSV : {chemin}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
