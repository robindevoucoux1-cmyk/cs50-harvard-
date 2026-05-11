"""Backend Instagram via Apify (recommande pour la production).

Deux actors utilises (officiels Apify) :
- apify/instagram-search-scraper : trouve un compte a partir d'un nom + ville
  Tarif : $1.50 / 1 000 resultats
- apify/instagram-scraper : scrape bio + posts d'un profil
  Tarif : $2.30 / 1 000 posts (~$0.014 pour 6 posts)

Pourquoi Apify plutot qu'instaloader :
- Aucun risque de ban de ton compte Insta perso
- Proxies + rotation IP gerees par Apify
- Vitesse cloud (100-200 posts/s pour apidojo)
- Free tier : $5/mois de credit -> ~3 000 recherches gratuites

Setup :
1. Compte Apify : https://console.apify.com/sign-up
2. Recupere ton token : https://console.apify.com/account/integrations
3. Mets-le dans .env : APIFY_TOKEN=apify_api_xxx
"""

import os
import re
from dataclasses import asdict, dataclass

from dotenv import load_dotenv

try:
    from apify_client import ApifyClient
except ImportError:  # pragma: no cover
    ApifyClient = None  # type: ignore[assignment]

load_dotenv()

ACTOR_SEARCH = "apify/instagram-search-scraper"
ACTOR_SCRAPER = "apify/instagram-scraper"

REGEX_HANDLE = re.compile(r"^[A-Za-z0-9_.]+$")


@dataclass
class PostInsta:
    date: str
    caption: str
    url_image: str
    nb_likes: int
    url_post: str


@dataclass
class ProfilInsta:
    handle: str
    nom_complet: str
    bio: str
    site_web: str
    categorie: str
    nb_followers: int
    nb_posts: int
    url_photo_profil: str
    posts: list[PostInsta]


def _client() -> "ApifyClient":
    if ApifyClient is None:
        raise RuntimeError("apify-client non installe. pip install apify-client")
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise RuntimeError(
            "APIFY_TOKEN manquant. Cree un .env avec APIFY_TOKEN=apify_api_xxx "
            "(token sur https://console.apify.com/account/integrations)."
        )
    return ApifyClient(token)


def cherche_handle(nom: str, ville: str, metier: str = "", max_resultats: int = 5) -> str | None:
    """Cherche un compte Insta a partir d'un nom de commerce + ville + metier.

    Strategie : on combine nom + ville + metier en requete texte.
    Le metier reduit drastiquement les faux positifs (ex: "Carpe Diem
    Bordeaux esthéticienne" filtre les crêperies en Idaho).
    Tarif : ~$0.0015 par appel.
    """
    client = _client()
    requete = " ".join(p for p in (nom, ville, metier) if p).strip()
    run_input = {
        "search": requete,
        "searchType": "user",
        "searchLimit": max_resultats,
    }
    try:
        run = client.actor(ACTOR_SEARCH).call(run_input=run_input)
    except Exception as e:  # noqa: BLE001
        print(f"    [apify-search-erreur] {nom}: {e}")
        return None

    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        handle = (item.get("username") or "").strip().lstrip("@").lower()
        if handle and REGEX_HANDLE.match(handle):
            return handle
    return None


def _normalise_post(raw: dict) -> PostInsta:
    return PostInsta(
        date=raw.get("timestamp") or "",
        caption=(raw.get("caption") or "")[:500],
        url_image=raw.get("displayUrl") or "",
        nb_likes=raw.get("likesCount") or 0,
        url_post=raw.get("url") or "",
    )


def scrape_profil(handle: str, max_posts: int = 6) -> ProfilInsta | None:
    """Scrape le profil complet d'un handle Insta.

    Strategie : un seul run avec resultsType=details qui renvoie un item
    "profile" contenant bio + un tableau latestPosts. Cout : ~$2.30/1k
    posts donc ~$0.014 pour bio + 6 posts.
    """
    client = _client()
    url = f"https://www.instagram.com/{handle}/"
    run_input = {
        "directUrls": [url],
        "resultsType": "details",
        "resultsLimit": max_posts,
        "addParentData": False,
    }
    try:
        run = client.actor(ACTOR_SCRAPER).call(run_input=run_input)
    except Exception as e:  # noqa: BLE001
        print(f"    [apify-scrape-erreur] @{handle}: {e}")
        return None

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    if not items:
        return None

    profil_brut = items[0]
    posts_bruts = profil_brut.get("latestPosts") or []
    posts = [_normalise_post(p) for p in posts_bruts[:max_posts]]

    return ProfilInsta(
        handle=handle,
        nom_complet=profil_brut.get("fullName") or "",
        bio=profil_brut.get("biography") or "",
        site_web=profil_brut.get("externalUrl") or "",
        categorie=profil_brut.get("businessCategoryName") or "",
        nb_followers=profil_brut.get("followersCount") or 0,
        nb_posts=profil_brut.get("postsCount") or 0,
        url_photo_profil=profil_brut.get("profilePicUrl") or "",
        posts=posts,
    )


def _normalise(s: str) -> str:
    """Lowercase + retire accents + garde lettres/chiffres/espaces."""
    import unicodedata
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "".join(c if c.isalnum() else " " for c in s)


def match_plausible(profil: ProfilInsta, nom: str, ville: str, metier: str = "") -> tuple[bool, str]:
    """Verifie si un profil scrape correspond vraiment au prospect cherche.

    Renvoie (ok, raison). Strict : il faut au moins 2 signaux sur 3 :
    1. Le nom commercial (ou un mot >=4 lettres) apparait dans nom_complet/bio/handle
    2. La ville apparait dans la bio
    3. Le metier (ou synonyme) apparait dans bio/categorie

    Sinon = faux positif probable (ex: meme nom mais mauvais pays).
    """
    blob = _normalise(" ".join([
        profil.handle,
        profil.nom_complet,
        profil.bio,
        profil.categorie,
        profil.site_web,
    ]))
    nom_norm = _normalise(nom)
    ville_norm = _normalise(ville)
    metier_norm = _normalise(metier)

    mots_nom_significatifs = [m for m in nom_norm.split() if len(m) >= 4]
    signal_nom = any(m in blob for m in mots_nom_significatifs) if mots_nom_significatifs else nom_norm in blob
    signal_ville = bool(ville_norm) and ville_norm in blob
    signal_metier = False
    if metier_norm:
        mots_metier = [m for m in metier_norm.split() if len(m) >= 4]
        signal_metier = any(m in blob for m in mots_metier) if mots_metier else metier_norm in blob
        synonymes = {
            "estheticienne": ["beaute", "beauty", "soin", "epilation", "institut"],
            "sophrologue": ["sophro", "relaxation", "bien etre"],
            "naturopathe": ["naturo", "naturopathie"],
            "coach": ["coaching", "fitness", "sport"],
        }
        for cle, syns in synonymes.items():
            if cle in metier_norm:
                signal_metier = signal_metier or any(s in blob for s in syns)

    score = sum([signal_nom, signal_ville, signal_metier])
    raison = f"nom={signal_nom} ville={signal_ville} metier={signal_metier}"
    return (score >= 2, raison)


def profil_to_dict(profil: ProfilInsta) -> dict:
    return {
        **{k: v for k, v in asdict(profil).items() if k != "posts"},
        "posts": [asdict(p) for p in profil.posts],
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python apify_scraper.py find 'Nom du salon' 'Ville'")
        print("  python apify_scraper.py scrape <handle>")
        sys.exit(1)

    action = sys.argv[1]
    if action == "find":
        nom, ville = sys.argv[2], sys.argv[3]
        h = cherche_handle(nom, ville)
        print(f"@{h}" if h else "Aucun compte trouve")
    elif action == "scrape":
        profil = scrape_profil(sys.argv[2])
        if profil:
            print(json.dumps(profil_to_dict(profil), indent=2, ensure_ascii=False))
        else:
            print("Profil non trouve")
    else:
        print(f"Action inconnue : {action}")
        sys.exit(1)
