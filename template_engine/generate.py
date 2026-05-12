#!/usr/bin/env python3
"""
Vitriz template engine. Genere un site HTML a partir d'un JSON + theme.

Usage :
    python generate.py sites/art-innel.json
    python generate.py sites/art-innel.json --theme medical-mint
    python generate.py sites/art-innel.json --out custom/output
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    sys.exit("Manque jinja2. Installe avec : pip install jinja2")

ROOT = Path(__file__).parent


def load_site(site_path: Path) -> dict:
    with open(site_path, encoding="utf-8") as f:
        return json.load(f)


def load_theme(theme_name: str) -> dict:
    theme_path = ROOT / "themes" / f"{theme_name}.json"
    if not theme_path.exists():
        available = sorted(p.stem for p in (ROOT / "themes").glob("*.json"))
        sys.exit(f"Theme inconnu : {theme_name}. Dispos : {', '.join(available)}")
    with open(theme_path, encoding="utf-8") as f:
        return json.load(f)


def render(site_path: Path, theme_override: str | None = None, out_dir: Path | None = None) -> Path:
    site = load_site(site_path)
    theme_name = theme_override or site.get("theme", "esthetique-rose")
    theme = load_theme(theme_name)

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    tmpl = env.get_template("base.html.j2")
    site_clean = {k: v for k, v in site.items() if k != "theme"}
    html = tmpl.render(theme=theme, **site_clean)

    slug = site.get("slug") or site_path.stem
    out_dir = out_dir or (ROOT / "output" / slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "index.html"
    out_file.write_text(html, encoding="utf-8")
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Vitriz template engine")
    parser.add_argument("site", help="Chemin vers le JSON du site (ex: sites/art-innel.json)")
    parser.add_argument("--theme", help="Override du theme (sinon utilise celui du JSON)")
    parser.add_argument("--out", help="Dossier de sortie (defaut: output/<slug>/)")
    args = parser.parse_args()

    site_path = Path(args.site)
    if not site_path.exists():
        sys.exit(f"Fichier introuvable : {site_path}")
    out_dir = Path(args.out) if args.out else None
    out_file = render(site_path, theme_override=args.theme, out_dir=out_dir)
    size_kb = out_file.stat().st_size // 1024
    print(f"OK {out_file} ({size_kb} KB)")


if __name__ == "__main__":
    main()
