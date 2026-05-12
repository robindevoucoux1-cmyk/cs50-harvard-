#!/usr/bin/env python3
"""
Lead Finder API : recherche de prospects par ville + metier via OSM,
avec classification de leur presence en ligne (Planity, Booksy, Insta, vrai site).

Reutilise lead_finder.py de la racine du projet, mais inverse la logique :
au lieu d'exclure les commerces avec website, on les INCLUT et on classifie
chaque URL pour identifier les vraies opportunites (= pas de vrai site).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import from existing lead_finder.py
from lead_finder import (
    construit_requete,
    interroge_overpass,
    resoud_metier,
    METIER_TO_OSM,
)
from config import VILLES


# Plateformes connues : domaine -> classification
PLATFORMS: dict[str, dict] = {
    "planity.com":      {"name": "Planity",     "type": "booking", "icon": "📅"},
    "booksy.com":       {"name": "Booksy",      "type": "booking", "icon": "📅"},
    "booksy.fr":        {"name": "Booksy",      "type": "booking", "icon": "📅"},
    "fresha.com":       {"name": "Fresha",      "type": "booking", "icon": "📅"},
    "treatwell.fr":     {"name": "Treatwell",   "type": "booking", "icon": "📅"},
    "treatwell.com":    {"name": "Treatwell",   "type": "booking", "icon": "📅"},
    "doctolib.fr":      {"name": "Doctolib",    "type": "booking", "icon": "🩺"},
    "kalendes.com":     {"name": "Kalendes",    "type": "booking", "icon": "📅"},
    "sumup.link":       {"name": "SumUp",       "type": "booking", "icon": "📅"},
    "instagram.com":    {"name": "Instagram",   "type": "social",  "icon": "📷"},
    "facebook.com":     {"name": "Facebook",    "type": "social",  "icon": "👥"},
    "linktr.ee":        {"name": "Linktree",    "type": "social",  "icon": "🔗"},
    "linkin.bio":       {"name": "Linkin.bio",  "type": "social",  "icon": "🔗"},
    "wix.com":          {"name": "Wix",         "type": "site",    "icon": "🌐"},
    "wixsite.com":      {"name": "Wix",         "type": "site",    "icon": "🌐"},
    "squarespace.com":  {"name": "Squarespace", "type": "site",    "icon": "🌐"},
    "webflow.io":       {"name": "Webflow",     "type": "site",    "icon": "🌐"},
    "shopify.com":      {"name": "Shopify",     "type": "site",    "icon": "🌐"},
    "myshopify.com":    {"name": "Shopify",     "type": "site",    "icon": "🌐"},
    "weebly.com":       {"name": "Weebly",      "type": "site",    "icon": "🌐"},
    "google.com":       {"name": "Google",      "type": "other",   "icon": "🔍"},
}


def classify_url(url: str) -> dict | None:
    if not url:
        return None
    u = url.lower()
    for domain, info in PLATFORMS.items():
        if domain in u:
            return {**info, "url": url, "is_real_site": info["type"] == "site"}
    # URL inconnue = on suppose que c'est un site custom (vrai site)
    return {"name": "Site personnel", "type": "site", "icon": "🌐", "url": url, "is_real_site": True}


def _normalize_insta(handle_or_url: str) -> str:
    """Returns full instagram URL."""
    if not handle_or_url:
        return ""
    if handle_or_url.startswith("http"):
        return handle_or_url
    return f"https://www.instagram.com/{handle_or_url.lstrip('@')}/"


def search_leads(city: str, metier: str, limit: int = 20, only_opportunities: bool = True) -> dict:
    """Search OSM and classify presence.

    Args:
        city: ville (ex 'Paris')
        metier: metier (ex 'esthéticienne')
        limit: nb max de resultats
        only_opportunities: si True, garde uniquement ceux SANS vrai site

    Returns:
        {'leads': [...], 'total': int, 'city': str, 'metier': str}
    """
    metier_norm, tags = resoud_metier(metier)
    if not tags:
        return {
            "error": f"Métier '{metier}' inconnu",
            "available": sorted(METIER_TO_OSM.keys()),
            "leads": [],
            "total": 0,
        }

    requete = construit_requete(city, tags)
    elements = interroge_overpass(requete)

    leads = []
    seen = set()

    for el in elements:
        t = el.get("tags", {})
        nom = (t.get("name") or "").strip()
        if not nom:
            continue
        if (nom, city) in seen:
            continue
        seen.add((nom, city))

        website = (
            t.get("website")
            or t.get("contact:website")
            or t.get("url")
            or t.get("contact:url")
            or ""
        )
        instagram = t.get("contact:instagram") or t.get("instagram", "")
        facebook = t.get("contact:facebook") or t.get("facebook", "")

        platforms = []
        website_class = classify_url(website) if website else None
        if website_class:
            platforms.append(website_class)
        if instagram:
            platforms.append({
                "name": "Instagram",
                "type": "social",
                "icon": "📷",
                "url": _normalize_insta(instagram),
                "is_real_site": False,
            })
        if facebook:
            platforms.append({
                "name": "Facebook",
                "type": "social",
                "icon": "👥",
                "url": facebook if facebook.startswith("http") else f"https://facebook.com/{facebook}",
                "is_real_site": False,
            })

        has_real_site = bool(website_class and website_class.get("is_real_site"))

        if only_opportunities and has_real_site:
            continue

        adresse_parts = [
            t.get("addr:housenumber", ""),
            t.get("addr:street", ""),
            t.get("addr:postcode", ""),
            t.get("addr:city", "") or city,
        ]
        adresse = " ".join(p for p in adresse_parts if p).strip()

        lat = el.get("lat")
        lon = el.get("lon")

        # Scoring : meilleur prospect = pas de vrai site + presence en ligne active
        score = 0
        if not has_real_site:
            score += 50
        if any(p.get("type") == "booking" for p in platforms):
            score += 25  # actif en booking = vrai business
        if instagram:
            score += 15
        if facebook:
            score += 5

        leads.append({
            "id": f"{city}-{nom}".lower().replace(" ", "-"),
            "nom": nom,
            "metier": metier_norm,
            "ville": city,
            "telephone": t.get("phone") or t.get("contact:phone", ""),
            "email": t.get("contact:email") or t.get("email", ""),
            "adresse": adresse,
            "lat": lat,
            "lon": lon,
            "lien_maps": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if lat else "",
            "website": website,
            "has_real_site": has_real_site,
            "platforms": platforms,
            "score": score,
            "planity_url": next((p["url"] for p in platforms if p["name"] == "Planity"), ""),
        })

    leads.sort(key=lambda x: -x["score"])
    return {
        "leads": leads[:limit],
        "total": len(leads),
        "city": city,
        "metier": metier_norm,
    }


def list_metiers() -> list[str]:
    return sorted(METIER_TO_OSM.keys())


def list_villes() -> list[str]:
    return sorted(VILLES)


if __name__ == "__main__":
    # Quick test
    import json as _json
    res = search_leads("Bordeaux", "esthéticienne", limit=10, only_opportunities=False)
    print(_json.dumps(res, indent=2, ensure_ascii=False))
