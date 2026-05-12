#!/usr/bin/env python3
"""
Maps a Planity scrape dict into a template_engine site.json structure.

Usage :
    python planity_to_site.py path/to/planity.json --slug nom-slug [--theme esthetique-rose]
    python planity_to_site.py path/to/planity.json --slug nom-slug --output sites/nom-slug.json
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def short_city(address: str) -> str:
    if not address:
        return ""
    # "7 Rue Lafaurie de Monbadon, 33000 Bordeaux" -> "Bordeaux"
    parts = [p.strip() for p in address.split(",")]
    if parts:
        last = parts[-1].strip()
        m = re.match(r"\d{5}\s+(.+)", last)
        if m:
            return m.group(1).strip()
        return last
    return ""


def format_note(note) -> str:
    if note is None:
        return ""
    try:
        return f"{float(note):.1f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(note)


def map_horaires(horaires: dict) -> str:
    """Convert horaires dict into HTML for contact card."""
    if not horaires:
        return ""
    jours_map = {
        "lundi": "Lun", "mardi": "Mar", "mercredi": "Mer",
        "jeudi": "Jeu", "vendredi": "Ven", "samedi": "Sam", "dimanche": "Dim",
    }
    lines = []
    week = ["lundi", "mardi", "mercredi", "jeudi", "vendredi"]
    weekend_open = []
    closed = []
    # Try to group weekday into one range
    week_values = [horaires.get(d, "Fermé") for d in week]
    if all(v == week_values[0] and v != "Fermé" for v in week_values):
        lines.append(f"Lun à Ven&nbsp;: {week_values[0]}")
    else:
        for d in week:
            v = horaires.get(d)
            if v and v != "Fermé":
                lines.append(f"{jours_map[d]}&nbsp;: {v}")
    for d in ["samedi", "dimanche"]:
        v = horaires.get(d)
        if v and v != "Fermé":
            lines.append(f"{jours_map[d]}&nbsp;: {v}")
        elif v == "Fermé":
            closed.append(jours_map[d])
    if closed:
        lines.append(f'<span style="opacity: 0.7;">{", ".join(closed)} fermé</span>')
    return "<br>\n        ".join(lines)


def map_services(services: dict) -> list:
    """Convert services dict (group -> [items]) into families[] structure."""
    if not services:
        return []
    families = []
    counter = 1
    for group_name, items in services.items():
        if not items:
            continue
        family = {"name": group_name, "items": []}
        for item in items:
            entry = {
                "num": f"{counter:02d}",
                "nom": item.get("nom", "").strip(),
                "duree": item.get("duree", "").strip(),
                "prix": item.get("prix", "").strip(),
            }
            note = item.get("note_longueurs") or item.get("note")
            if note:
                entry["note"] = note.strip()
            family["items"].append(entry)
            counter += 1
        families.append(family)
    return families


def map_offre_phare(offre: dict) -> dict | None:
    if not offre:
        return None
    nom = offre.get("nom", "Offre combo")
    reduction = offre.get("reduction", "")
    description = offre.get("description", "")
    badge = f"-{reduction}" if reduction else ""
    return {
        "lbl": "Offre combo",
        "title": nom,
        "description": description,
        "badge": badge,
        "badge_small": "sur la réservation" if badge else "",
    }


def planity_to_site(planity: dict, slug: str, theme: str = "esthetique-rose") -> dict:
    nom = (planity.get("nom") or "").strip()
    nom_display = nom
    # Pretty case if all-caps with underscore (ART_INNEL -> Art Innel)
    if re.match(r"^[A-Z_0-9 ]+$", nom):
        nom_display = " ".join(w.capitalize() for w in re.split(r"[_\s]+", nom))

    adresse = planity.get("adresse", "")
    city = short_city(adresse)
    url = planity.get("url", "")
    note = planity.get("note")
    nb_avis = planity.get("nb_avis", 0)
    horaires = planity.get("horaires", {})
    services = planity.get("services") or {}
    offre = planity.get("offre_phare") or {}
    telephone = (planity.get("telephone") or "").strip()
    insta = planity.get("instagram") or f"@{slug.replace('-', '_')}"

    site = {
        "slug": slug,
        "theme": theme,
        "brand": {
            "name": nom_display,
            "name_html": _name_html(nom_display),
            "title": f"{nom_display}, {city}".rstrip(", "),
            "meta_description": f"{nom_display} à {city}. Réservation en ligne sur Planity.",
            "og_title": f"{nom_display}, {city}".rstrip(", "),
            "og_description": f"{nom_display}. Réservation en ligne sur Planity.",
            "og_image": "assets/post_004.jpg",
            "favicon": "assets/profil.jpg",
            "footer_description": f"{nom_display}. {city}.",
            "copyright_name": nom_display,
        },
        "nav": [
            {"label": "L'approche", "href": "#approche"},
            {"label": "Soins", "href": "#protocoles"},
            {"label": "Questions", "href": "#questions"},
            {"label": "Contact", "href": "#contact"},
        ],
        "cta_primary": {
            "label_long": "Réserver sur Planity",
            "label_short": "Réserver",
            "url": url,
        },
        "hero": {
            "eyebrow_num": "01",
            "eyebrow_text": city,
            "h1_html": f"<em class=\"acc\">{nom_display}.</em>",
            "tagline": f"{nom_display} à {city}. Réservation en ligne sur Planity.",
            "ctas": [
                {"label": "Réserver sur Planity", "url": url, "style": "primary", "external": True},
                {"label": "Voir les soins", "url": "#protocoles", "style": "light"},
            ],
            "image": {
                "src": "assets/post_004.jpg",
                "alt": f"{nom_display}, {city}",
                "caption": city,
            },
        },
        "marquee": {
            "tags": _extract_tags(services),
        },
        "about": {
            "id": "approche",
            "eyebrow_num": "02",
            "eyebrow_text": "L'approche",
            "h2_html": "Bienvenue.",
            "signature": f"{nom_display}. {city}.",
            "paragraphs": [
                f"{nom_display}, {city}. Réservation en ligne sur Planity.",
                "[À compléter : description de l'institut, savoir-faire, ambiance]",
            ],
        },
        "services": {
            "id": "protocoles",
            "eyebrow_num": "03",
            "eyebrow_text": "Les soins",
            "h2_html": "Le catalogue,<br>en détail.",
            "intro": f"{_count_services(services)} prestations, regroupées en {len(services)} familles.",
            "families": map_services(services),
        },
        "faq": {
            "id": "questions",
            "eyebrow_num": "05",
            "eyebrow_text": "Questions",
            "h2_html": "Les questions<br>qui reviennent.",
            "items": [
                {"q": "Comment réserver ?", "a": f"En ligne sur Planity : <a href=\"{url}\" target=\"_blank\">{url}</a>"},
                {"q": "Où se trouve l'institut ?", "a": f"{adresse}"},
            ],
        },
        "contact": {
            "id": "contact",
            "eyebrow_num": "06",
            "eyebrow_text": "Contact",
            "h2_html": "Prendre rendez-vous.",
            "intro": "Réservation en ligne sur Planity.",
            "cards": _contact_cards(url, adresse, telephone, horaires),
        },
        "footer": {
            "coords": [
                {"label": "Réserver sur Planity ↗", "url": url, "external": True},
            ],
        },
    }

    # Reviews section only if note exists
    if note is not None and nb_avis:
        site["reviews"] = {
            "eyebrow_num": "04",
            "eyebrow_text": "Sur Planity",
            "score": format_note(note),
            "max": "5",
            "label": f"Note moyenne sur {nb_avis} avis Planity",
            "link_label": "Lire les avis sur Planity",
            "link_url": url,
        }

    # Offre phare
    offre_banner = map_offre_phare(offre)
    if offre_banner:
        site["services"]["offre_banner"] = offre_banner

    # Insta link
    insta_handle = insta.lstrip("@")
    site["footer"]["coords"].append({
        "label": f"@{insta_handle}",
        "url": f"https://www.instagram.com/{insta_handle}/",
        "external": True,
    })

    return site


def _name_html(name: str) -> str:
    parts = name.split(" ", 1)
    if len(parts) == 2:
        return f"{parts[0]} <em>{parts[1]}</em>"
    return name


def _extract_tags(services: dict) -> list:
    tags = []
    for items in services.values():
        for item in items[:2]:
            n = item.get("nom", "").strip()
            n = re.sub(r"\s*\([^)]*\)\s*", "", n)
            if n and len(n) < 30:
                tags.append(n)
        if len(tags) >= 5:
            break
    return tags[:5] or ["Prestations", "Soins"]


def _count_services(services: dict) -> str:
    n = sum(len(v) for v in services.values() if isinstance(v, list))
    return _number_to_word(n) if n < 30 else str(n)


_NUMBERS = {
    1: "Une", 2: "Deux", 3: "Trois", 4: "Quatre", 5: "Cinq", 6: "Six",
    7: "Sept", 8: "Huit", 9: "Neuf", 10: "Dix", 11: "Onze", 12: "Douze",
    13: "Treize", 14: "Quatorze", 15: "Quinze", 16: "Seize",
    17: "Dix-sept", 18: "Dix-huit", 19: "Dix-neuf", 20: "Vingt",
    21: "Vingt et une", 25: "Vingt-cinq", 26: "Vingt-six",
}


def _number_to_word(n: int) -> str:
    return _NUMBERS.get(n, str(n))


def _contact_cards(url: str, adresse: str, telephone: str, horaires: dict) -> list:
    cards = [
        {
            "lbl": "Réserver en ligne",
            "val_html": f'<a href="{url}" target="_blank" rel="noopener">Sur Planity ↗</a>',
        }
    ]
    if telephone:
        cards.append({
            "lbl": "Téléphone",
            "val_html": telephone.replace(" ", "&nbsp;"),
        })
    if adresse:
        cards.append({
            "lbl": "Sur place",
            "val_html": adresse.replace(", ", ",<br>"),
        })
    if horaires:
        cards.append({
            "lbl": "Horaires",
            "val_html": map_horaires(horaires),
            "style": "font-size: 15px; line-height: 1.6;",
        })
    return cards[:3] if len(cards) > 3 else cards


def main():
    parser = argparse.ArgumentParser(description="Map Planity JSON to site.json")
    parser.add_argument("planity_json", help="Chemin vers planity.json (output du scraper)")
    parser.add_argument("--slug", help="Slug du site (defaut: derive du nom)")
    parser.add_argument("--theme", default="esthetique-rose", help="Theme a utiliser")
    parser.add_argument("--output", help="Output path (defaut: sites/<slug>.json)")
    args = parser.parse_args()

    src = Path(args.planity_json)
    if not src.exists():
        sys.exit(f"Fichier introuvable : {src}")
    data = json.loads(src.read_text(encoding="utf-8"))
    slug = args.slug or slugify(data.get("nom", "site"))
    site = planity_to_site(data, slug, theme=args.theme)

    out = Path(args.output) if args.output else (ROOT / "sites" / f"{slug}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OK {out}")


if __name__ == "__main__":
    main()
