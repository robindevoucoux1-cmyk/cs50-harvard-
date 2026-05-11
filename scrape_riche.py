"""Re-scrape complet d'un profil Insta + telechargement local des images.

Sortie : output/sites/<slug>/
    assets/
        profil.jpg
        post_001.jpg ... post_030.jpg
    metadata.json (bio, fullName, externalUrl, posts avec captions/likes/dates)

Pourquoi local : les URLs CDN Instagram expirent en quelques heures, donc
on doit telecharger juste apres le scrape pour pouvoir reutiliser plus
tard (vision IA, generation de site).

Cout : 30 posts * $2.30/1000 = $0.069 par lead.
"""

import json
import re
import sys
import time
import unicodedata
from dataclasses import asdict
from pathlib import Path

import requests

from apify_scraper import ProfilInsta, PostInsta, _client


def slugifie(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "lead"


def _telecharge(url: str, chemin: Path, retries: int = 3, timeout: int = 30) -> bool:
    """Telecharge une URL vers un fichier local. Retourne True si OK."""
    if not url:
        return False
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0)"}
    for tentative in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, stream=True)
            r.raise_for_status()
            chemin.write_bytes(r.content)
            return True
        except Exception as e:  # noqa: BLE001
            if tentative == retries - 1:
                print(f"    [download-fail] {chemin.name}: {e}")
                return False
            time.sleep(1.5 ** tentative)
    return False


def scrape_complet(handle: str, dossier_sortie: Path, max_posts: int = 30) -> dict | None:
    """Re-scrape complet + telechargement local des images.

    Renvoie le dict metadata, ou None si echec. Cree :
        dossier_sortie/assets/profil.jpg
        dossier_sortie/assets/post_001.jpg ... post_NNN.jpg
        dossier_sortie/metadata.json
    """
    client = _client()
    url_profil = f"https://www.instagram.com/{handle}/"

    print(f"  [scrape] @{handle} ({max_posts} posts)...")
    run_input = {
        "directUrls": [url_profil],
        "resultsType": "details",
        "resultsLimit": max_posts,
        "addParentData": False,
    }
    run = client.actor("apify/instagram-scraper").call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    if not items:
        print(f"    [scrape-fail] @{handle}: pas de resultat")
        return None

    profil_brut = items[0]
    posts_bruts = profil_brut.get("latestPosts") or []
    print(f"    profil OK, {len(posts_bruts)} posts retournes")

    assets = dossier_sortie / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    # photo de profil
    url_pp = profil_brut.get("profilePicUrlHD") or profil_brut.get("profilePicUrl") or ""
    _telecharge(url_pp, assets / "profil.jpg")

    # posts : on telecharge image et garde metadata
    posts_meta = []
    for i, p in enumerate(posts_bruts[:max_posts], 1):
        url_img = p.get("displayUrl") or ""
        if not url_img:
            continue
        nom_fichier = f"post_{i:03d}.jpg"
        ok = _telecharge(url_img, assets / nom_fichier)
        if not ok:
            continue
        posts_meta.append({
            "fichier": f"assets/{nom_fichier}",
            "url_originale": url_img,
            "url_post": p.get("url") or "",
            "date": p.get("timestamp") or "",
            "type": p.get("type") or "",
            "caption": (p.get("caption") or "")[:1000],
            "nb_likes": p.get("likesCount") or 0,
            "nb_commentaires": p.get("commentsCount") or 0,
            "hashtags": p.get("hashtags") or [],
            "mentions": p.get("mentions") or [],
            "alt_text": p.get("alt") or "",
        })

    metadata = {
        "handle": handle,
        "url_profil": url_profil,
        "fullName": profil_brut.get("fullName") or "",
        "biography": profil_brut.get("biography") or "",
        "externalUrl": profil_brut.get("externalUrl") or "",
        "businessCategoryName": profil_brut.get("businessCategoryName") or "",
        "followersCount": profil_brut.get("followersCount") or 0,
        "followsCount": profil_brut.get("followsCount") or 0,
        "postsCount": profil_brut.get("postsCount") or 0,
        "verified": profil_brut.get("verified", False),
        "isBusinessAccount": profil_brut.get("isBusinessAccount", False),
        "private": profil_brut.get("private", False),
        "profilePicUrl": url_pp,
        "posts": posts_meta,
    }

    (dossier_sortie / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"    sauve : {len(posts_meta)} photos + metadata.json -> {dossier_sortie}")
    return metadata


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scrape_riche.py <handle> [<max_posts>]")
        return 1
    handle = sys.argv[1].lstrip("@")
    max_posts = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    dossier = Path("output/sites") / slugifie(handle)
    metadata = scrape_complet(handle, dossier, max_posts)
    if not metadata:
        return 1
    print(f"\nResume :")
    print(f"  Nom        : {metadata['fullName']}")
    print(f"  Followers  : {metadata['followersCount']}")
    print(f"  Posts      : {len(metadata['posts'])} telecharges")
    print(f"  Categorie  : {metadata['businessCategoryName']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
