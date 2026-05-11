"""Analyse les sites concurrents (meme ville + meme metier).

Pipeline :
1. Trouve 10-20 concurrents AVEC site web via OSM (inverse du lead_finder).
2. Aspire chaque site (HTML).
3. Extrait : titres, sections, services, couleurs, polices, CTA, structure menu.
4. Sort un rapport JSON + Markdown lisible.

Usage:
    python competitor_analyzer.py --ville Bordeaux --metier esthéticienne
    python competitor_analyzer.py --ville Lyon --metier naturopathe --max 15
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from lead_finder import (
    HEADERS,
    construit_requete,
    interroge_overpass,
    resoud_metier,
)

UA_NAVIGATEUR = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

COULEURS_NEUTRES = {
    "#000", "#fff", "#000000", "#ffffff",
    "#111", "#222", "#333", "#444", "#555", "#666", "#777", "#888", "#999",
    "#aaa", "#bbb", "#ccc", "#ddd", "#eee", "#f0f0f0", "#fafafa", "#f5f5f5",
}
POLICES_GENERIQUES = {
    "inherit", "initial", "unset", "revert",
    "sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui",
    "-apple-system", "blinkmacsystemfont",
}
MOTS_PAGES_TYPIQUES = {
    "accueil", "home", "à propos", "a propos", "about",
    "services", "prestations", "soins", "tarifs", "tarif", "prix",
    "contact", "blog", "actualités", "actualites", "galerie", "réalisations",
    "réserver", "reserver", "rendez-vous", "boutique", "shop",
    "team", "équipe", "equipe",
}

REGEX_COULEUR_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
REGEX_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}\"']+)", re.IGNORECASE)


def trouve_concurrents_avec_site(ville: str, metier: str, maximum: int = 20) -> list[dict]:
    """Reutilise OSM mais filtre les commerces AVEC site web."""
    _, tags = resoud_metier(metier)
    if not tags:
        print(f"Pas de mapping OSM pour '{metier}'", file=sys.stderr)
        return []

    requete = construit_requete(ville, tags)
    elements = interroge_overpass(requete)

    concurrents = []
    vus = set()
    for el in elements:
        t = el.get("tags", {})
        nom = t.get("name")
        site = t.get("website") or t.get("contact:website") or t.get("url") or t.get("contact:url")
        if not nom or not site:
            continue
        if not site.startswith(("http://", "https://")):
            site = f"https://{site}"
        domaine = urlparse(site).netloc.lower().replace("www.", "")
        if not domaine or domaine in vus:
            continue
        vus.add(domaine)
        concurrents.append({"nom": nom, "site": site, "domaine": domaine})
        if len(concurrents) >= maximum:
            break
    return concurrents


def aspire_site(url: str) -> tuple[str, str] | None:
    """Telecharge HTML + CSS inline. Renvoie (html, css_aggrege) ou None."""
    try:
        r = requests.get(url, headers=UA_NAVIGATEUR, timeout=15, allow_redirects=True)
        r.raise_for_status()
        html = r.text
    except requests.RequestException as e:
        print(f"  [echec] {url}: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(html, "lxml")
    css_morceaux = [style.get_text() for style in soup.find_all("style")]
    return html, "\n".join(css_morceaux)


def extrait_textes(soup: BeautifulSoup) -> dict:
    titre = soup.title.get_text(strip=True) if soup.title else ""
    meta_desc = ""
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        meta_desc = md["content"].strip()

    h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")][:5]
    h2 = [h.get_text(" ", strip=True) for h in soup.find_all("h2")][:10]
    h3 = [h.get_text(" ", strip=True) for h in soup.find_all("h3")][:10]

    return {"titre": titre, "meta_description": meta_desc, "h1": h1, "h2": h2, "h3": h3}


def extrait_navigation(soup: BeautifulSoup) -> list[str]:
    """Recupere les liens de menu (pages typiques du site)."""
    liens = []
    for nav in soup.find_all(["nav", "header"]):
        for a in nav.find_all("a"):
            texte = a.get_text(" ", strip=True)
            if not (2 <= len(texte) <= 30):
                continue
            mots = texte.split()
            if len(mots) > 3:
                continue
            tl = texte.lower()
            ressemble_page = (
                tl in MOTS_PAGES_TYPIQUES
                or any(mot in tl for mot in MOTS_PAGES_TYPIQUES)
            )
            if ressemble_page:
                liens.append(texte)
    return list(dict.fromkeys(liens))[:15]


def extrait_ctas(soup: BeautifulSoup) -> list[str]:
    """Boutons et liens d'action principaux."""
    ctas = []
    for el in soup.find_all(["button", "a"]):
        texte = el.get_text(" ", strip=True)
        classes = " ".join(el.get("class") or [])
        est_cta = (
            any(mot in classes.lower() for mot in ["btn", "button", "cta", "action"])
            or any(mot in texte.lower() for mot in ["réserver", "rendez-vous", "contact", "devis", "appeler"])
        )
        if est_cta and 3 <= len(texte) <= 40:
            ctas.append(texte)
    return list(dict.fromkeys(ctas))[:10]


def extrait_couleurs(html: str, css: str) -> list[str]:
    """Top couleurs hex mentionnees dans HTML/CSS, hors neutres."""
    couleurs = REGEX_COULEUR_HEX.findall(html + " " + css)
    couleurs = [c.lower() for c in couleurs if c.lower() not in COULEURS_NEUTRES]
    return [c for c, _ in Counter(couleurs).most_common(5)]


def extrait_polices(html: str, css: str) -> list[str]:
    """Familles de polices declarees, hors generiques."""
    matches = REGEX_FONT_FAMILY.findall(html + " " + css)
    polices = []
    for m in matches:
        premiere = m.split(",")[0].strip().strip("\"'")
        if not premiere or len(premiere) >= 40:
            continue
        if premiere.lower() in POLICES_GENERIQUES:
            continue
        polices.append(premiere)
    return [p for p, _ in Counter(polices).most_common(3)]


def detecte_services(soup: BeautifulSoup) -> list[str]:
    """Heuristique : items de liste sous un titre type 'services/prestations/tarifs'."""
    services = []
    mots_cles = ["service", "prestation", "tarif", "soin", "séance", "formule"]
    for titre in soup.find_all(["h2", "h3", "h4"]):
        texte = titre.get_text(" ", strip=True).lower()
        if any(mc in texte for mc in mots_cles):
            suivant = titre.find_next(["ul", "ol", "div"])
            if suivant:
                for li in suivant.find_all("li")[:8]:
                    t = li.get_text(" ", strip=True)
                    if 3 <= len(t) <= 80:
                        services.append(t)
    return list(dict.fromkeys(services))[:15]


def analyse_un_site(concurrent: dict) -> dict:
    print(f"  -> {concurrent['domaine']}...", end=" ", flush=True)
    res = aspire_site(concurrent["site"])
    if not res:
        return {**concurrent, "erreur": "fetch_failed"}
    html, css = res
    soup = BeautifulSoup(html, "lxml")

    rapport = {
        **concurrent,
        **extrait_textes(soup),
        "navigation": extrait_navigation(soup),
        "ctas": extrait_ctas(soup),
        "services": detecte_services(soup),
        "couleurs": extrait_couleurs(html, css),
        "polices": extrait_polices(html, css),
    }
    print("OK")
    return rapport


def synthese(rapports: list[dict]) -> dict:
    """Aggrege les patterns recurrents pour servir de baseline."""
    valides = [r for r in rapports if "erreur" not in r]
    if not valides:
        return {"erreur": "aucun_site_analyse"}

    compte_pages = Counter(p.lower() for r in valides for p in r.get("navigation", []))
    compte_ctas = Counter(c.lower() for r in valides for c in r.get("ctas", []))
    compte_couleurs = Counter(c for r in valides for c in r.get("couleurs", []))
    compte_polices = Counter(p for r in valides for p in r.get("polices", []))

    return {
        "nb_sites_analyses": len(valides),
        "pages_recurrentes": [{"page": p, "frequence": n} for p, n in compte_pages.most_common(10)],
        "ctas_recurrents": [{"cta": c, "frequence": n} for c, n in compte_ctas.most_common(10)],
        "couleurs_dominantes": [{"hex": c, "frequence": n} for c, n in compte_couleurs.most_common(8)],
        "polices_dominantes": [{"police": p, "frequence": n} for p, n in compte_polices.most_common(5)],
        "tous_services_detectes": list(dict.fromkeys(s for r in valides for s in r.get("services", []))),
    }


def ecrit_markdown(synth: dict, rapports: list[dict], ville: str, metier: str, chemin: Path) -> None:
    lignes = [
        f"# Analyse concurrence - {metier} a {ville}\n",
        f"**Sites analyses :** {synth.get('nb_sites_analyses', 0)}\n",
        "\n## Pages recurrentes (menu)\n",
    ]
    for item in synth.get("pages_recurrentes", []):
        lignes.append(f"- {item['page']} ({item['frequence']}x)")
    lignes.append("\n## CTAs frequents (textes de boutons)\n")
    for item in synth.get("ctas_recurrents", []):
        lignes.append(f"- \"{item['cta']}\" ({item['frequence']}x)")
    lignes.append("\n## Couleurs dominantes\n")
    for item in synth.get("couleurs_dominantes", []):
        lignes.append(f"- `{item['hex']}` ({item['frequence']}x)")
    lignes.append("\n## Polices dominantes\n")
    for item in synth.get("polices_dominantes", []):
        lignes.append(f"- {item['police']} ({item['frequence']}x)")
    lignes.append("\n## Services / prestations detectes\n")
    for s in synth.get("tous_services_detectes", [])[:30]:
        lignes.append(f"- {s}")
    lignes.append("\n## Sites sources\n")
    for r in rapports:
        statut = "ERREUR" if "erreur" in r else "ok"
        lignes.append(f"- [{r['nom']}]({r['site']}) - {statut}")

    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("\n".join(lignes), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyse les concurrents d'une ville/metier.")
    parser.add_argument("--ville", required=True)
    parser.add_argument("--metier", required=True)
    parser.add_argument("--max", type=int, default=15, help="Nombre max de concurrents a analyser")
    parser.add_argument("--output-dir", default="output", help="Dossier de sortie")
    args = parser.parse_args()

    print(f"Recherche concurrents : {args.metier} a {args.ville}\n")
    concurrents = trouve_concurrents_avec_site(args.ville, args.metier, maximum=args.max)
    print(f"{len(concurrents)} concurrents avec site trouves\n")

    if not concurrents:
        print("Aucun concurrent a analyser.")
        return 1

    print("Analyse de chaque site :")
    rapports = []
    for c in concurrents:
        rapports.append(analyse_un_site(c))
        time.sleep(0.5)

    synth = synthese(rapports)

    slug = f"{args.ville.lower()}_{args.metier.lower().replace(' ', '_')}"
    base = Path(args.output_dir)
    base.mkdir(parents=True, exist_ok=True)
    (base / f"concurrents_{slug}.json").write_text(
        json.dumps({"synthese": synth, "details": rapports}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ecrit_markdown(synth, rapports, args.ville, args.metier, base / f"concurrents_{slug}.md")
    print(f"\nRapport ecrit : {base / f'concurrents_{slug}.md'}")
    print(f"Donnees brutes : {base / f'concurrents_{slug}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
