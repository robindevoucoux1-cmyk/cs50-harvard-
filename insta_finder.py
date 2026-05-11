"""Trouve le handle Instagram d'un commerce via plusieurs moteurs de recherche.

Strategie : essaie successivement DuckDuckGo, Brave, Bing jusqu'a trouver
un resultat. Sur la machine du user (pas en sandbox), au moins un fonctionne.

Sandbox local : les moteurs sont souvent bloques, c'est attendu.
"""

import re
import time
from typing import Callable

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

REGEX_HANDLE = re.compile(r"instagram\.com/([A-Za-z0-9_.]+)/?", re.IGNORECASE)
HANDLES_GENERIQUES = {
    "p", "reel", "reels", "stories", "explore", "tags",
    "accounts", "directory", "about", "developer", "press",
}


def extrait_handle(url_ou_texte: str) -> str | None:
    match = REGEX_HANDLE.search(url_ou_texte)
    if not match:
        return None
    handle = match.group(1).lower().strip(".")
    if handle in HANDLES_GENERIQUES or len(handle) < 2:
        return None
    return handle


def _premier_handle_dans(texte: str) -> str | None:
    for url in REGEX_HANDLE.findall(texte):
        h = url.lower().strip(".")
        if h not in HANDLES_GENERIQUES and len(h) >= 2:
            return h
    return None


def _ddg_html(requete: str) -> str | None:
    r = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": requete},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    return _premier_handle_dans(r.text)


def _ddg_lite(requete: str) -> str | None:
    r = requests.get(
        "https://lite.duckduckgo.com/lite/",
        params={"q": requete},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    return _premier_handle_dans(r.text)


def _brave(requete: str) -> str | None:
    r = requests.get(
        "https://search.brave.com/search",
        params={"q": requete},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    return _premier_handle_dans(r.text)


def _bing(requete: str) -> str | None:
    r = requests.get(
        "https://www.bing.com/search",
        params={"q": requete},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    return _premier_handle_dans(r.text)


MOTEURS: list[tuple[str, Callable[[str], str | None]]] = [
    ("duckduckgo", _ddg_html),
    ("ddg-lite", _ddg_lite),
    ("brave", _brave),
    ("bing", _bing),
]


def cherche_handle(nom: str, ville: str) -> str | None:
    """Tente plusieurs moteurs. Renvoie le premier handle Insta trouve."""
    requete = f'site:instagram.com "{nom}" {ville}'
    for nom_moteur, fonction in MOTEURS:
        try:
            handle = fonction(requete)
            if handle:
                return handle
        except requests.RequestException:
            time.sleep(2)
            continue
    return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python insta_finder.py 'Nom du salon' 'Ville'")
        sys.exit(1)
    nom, ville = sys.argv[1], sys.argv[2]
    handle = cherche_handle(nom, ville)
    print(f"@{handle}" if handle else "Aucun compte trouve")
