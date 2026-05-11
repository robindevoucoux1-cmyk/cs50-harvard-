"""Backend Instagram via Apify (recommande pour la production).

Deux actors utilises :
- apify/instagram-search-scraper : trouve un compte a partir d'un nom + ville
  Tarif : $1.50 / 1 000 resultats
- apidojo/instagram-scraper : scrape bio + posts d'un profil
  Tarif : $0.50 / 1 000 posts

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
ACTOR_SCRAPER = "apidojo/instagram-scraper"

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


def cherche_handle(nom: str, ville: str, max_resultats: int = 5) -> str | None:
    """Cherche un compte Insta a partir d'un nom de commerce + ville.

    Strategie : on combine nom + ville en requete texte, type user.
    On retient le premier resultat plausible (handle bien forme).
    Tarif : ~$0.0015 par appel.
    """
    client = _client()
    requete = f"{nom} {ville}".strip()
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
        date=raw.get("timestamp") or raw.get("takenAt") or "",
        caption=(raw.get("caption") or "")[:500],
        url_image=raw.get("displayUrl") or raw.get("imageUrl") or "",
        nb_likes=raw.get("likesCount") or raw.get("likes") or 0,
        url_post=raw.get("url") or raw.get("permalink") or "",
    )


def scrape_profil(handle: str, max_posts: int = 6) -> ProfilInsta | None:
    """Scrape le profil complet d'un handle Insta.

    Tarif : ~$0.0005 par post + le profil. Soit ~$0.0035 pour bio + 6 posts.
    """
    client = _client()
    url = f"https://www.instagram.com/{handle}/"
    run_input = {
        "startUrls": [url],
        "maxItems": max_posts + 1,
    }
    try:
        run = client.actor(ACTOR_SCRAPER).call(run_input=run_input)
    except Exception as e:  # noqa: BLE001
        print(f"    [apify-scrape-erreur] @{handle}: {e}")
        return None

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    if not items:
        return None

    profil_brut = next((i for i in items if i.get("type") == "profile" or i.get("biography") is not None), items[0])
    posts_bruts = [i for i in items if (i.get("type") in {"post", "reel"}) or i.get("caption") is not None]
    posts = [_normalise_post(p) for p in posts_bruts[:max_posts]]

    return ProfilInsta(
        handle=handle,
        nom_complet=profil_brut.get("fullName") or profil_brut.get("full_name") or "",
        bio=profil_brut.get("biography") or profil_brut.get("bio") or "",
        site_web=profil_brut.get("externalUrl") or profil_brut.get("website") or "",
        categorie=profil_brut.get("businessCategoryName") or profil_brut.get("category") or "",
        nb_followers=profil_brut.get("followersCount") or profil_brut.get("followers") or 0,
        nb_posts=profil_brut.get("postsCount") or profil_brut.get("mediaCount") or 0,
        url_photo_profil=profil_brut.get("profilePicUrl") or profil_brut.get("profilePictureUrl") or "",
        posts=posts,
    )


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
