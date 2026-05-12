#!/usr/bin/env python3
"""
Vitriz Dashboard - FastAPI backend.

Lance avec :
    cd dashboard && uvicorn server:app --reload --port 8000

Puis ouvre http://localhost:8000 dans Chrome.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
TE = ROOT / "template_engine"
SITES_DIR = TE / "sites"
THEMES_DIR = TE / "themes"
OUT_DIR = TE / "output"
DOCS_DIR = ROOT / "docs"

SLUG_RE = re.compile(r"^[a-z0-9-]+$")

app = FastAPI(title="Vitriz Dashboard")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _safe_slug(slug: str) -> str:
    if not SLUG_RE.match(slug):
        raise HTTPException(400, "Slug invalide")
    return slug


def _ensure_generated(slug: str) -> Path:
    site_json = SITES_DIR / f"{slug}.json"
    if not site_json.exists():
        raise HTTPException(404, f"Site inconnu : {slug}")
    out = OUT_DIR / slug / "index.html"
    if not out.exists():
        subprocess.run(
            [sys.executable, str(TE / "generate.py"), str(site_json)],
            check=True,
            capture_output=True,
        )
    return out


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(Path(__file__).parent / "templates" / "index.html")


@app.get("/api/sites")
def list_sites():
    out = []
    for f in sorted(SITES_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({
                "slug": f.stem,
                "name": d.get("brand", {}).get("name", f.stem),
                "theme": d.get("theme", "esthetique-rose"),
                "city": d.get("hero", {}).get("eyebrow_text", ""),
            })
        except Exception as e:
            out.append({"slug": f.stem, "name": f.stem, "error": str(e)})
    return out


@app.get("/api/sites/{slug}")
def get_site(slug: str):
    slug = _safe_slug(slug)
    p = SITES_DIR / f"{slug}.json"
    if not p.exists():
        raise HTTPException(404)
    return json.loads(p.read_text(encoding="utf-8"))


class SaveRequest(BaseModel):
    data: dict


@app.put("/api/sites/{slug}")
def save_site(slug: str, body: SaveRequest):
    slug = _safe_slug(slug)
    p = SITES_DIR / f"{slug}.json"
    if not p.exists():
        raise HTTPException(404)
    p.write_text(json.dumps(body.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True}


@app.post("/api/sites/{slug}/regenerate")
def regenerate(slug: str):
    slug = _safe_slug(slug)
    site_json = SITES_DIR / f"{slug}.json"
    if not site_json.exists():
        raise HTTPException(404)
    try:
        r = subprocess.run(
            [sys.executable, str(TE / "generate.py"), str(site_json)],
            check=True,
            capture_output=True,
            text=True,
        )
        return {"ok": True, "stdout": r.stdout.strip()}
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Erreur generate : {e.stderr}")


@app.get("/api/themes")
def list_themes():
    out = []
    for f in sorted(THEMES_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        out.append({
            "name": f.stem,
            "profession": d.get("profession", ""),
            "description": d.get("description", ""),
            "accent": d.get("colors", {}).get("accent", ""),
            "paper": d.get("colors", {}).get("paper", ""),
            "ink": d.get("colors", {}).get("ink-strong", ""),
            "display_font": d.get("fonts", {}).get("display", ""),
        })
    return out


@app.get("/preview/{slug}/")
@app.get("/preview/{slug}")
def preview(slug: str):
    slug = _safe_slug(slug)
    out = _ensure_generated(slug)
    return FileResponse(out, media_type="text/html")


@app.get("/preview/{slug}/{path:path}")
def preview_asset(slug: str, path: str):
    slug = _safe_slug(slug)
    if ".." in path:
        raise HTTPException(400)
    candidates = [
        OUT_DIR / slug / path,
        DOCS_DIR / slug / path,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return FileResponse(c)
    raise HTTPException(404)


def deep_merge(base: dict, patch) -> dict:
    """Deep merge a patch dict into a base dict. Returns new dict."""
    if not isinstance(patch, dict):
        return patch
    out = dict(base) if isinstance(base, dict) else {}
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class ChatRequest(BaseModel):
    slug: str
    message: str
    apply: bool = False


@app.post("/api/chat")
def chat(req: ChatRequest):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(400, "ANTHROPIC_API_KEY manquante dans dashboard/.env")

    slug = _safe_slug(req.slug)
    site_path = SITES_DIR / f"{slug}.json"
    if not site_path.exists():
        raise HTTPException(404)
    site_data = json.loads(site_path.read_text(encoding="utf-8"))

    themes = [f.stem for f in sorted(THEMES_DIR.glob("*.json"))]

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    system = f"""Tu aides un utilisateur a modifier le contenu d'un site web vitrine.
Le site est decrit par un JSON. Voici le JSON actuel :

```json
{json.dumps(site_data, indent=2, ensure_ascii=False)}
```

Themes disponibles : {", ".join(themes)}

L'utilisateur va te demander des modifications en francais.
Tu dois repondre UNIQUEMENT avec un objet JSON au format suivant, sans markdown, sans autre texte :

{{
  "explanation": "courte explication en francais de ce que tu vas modifier",
  "patch": {{ ... }}
}}

Le "patch" est un objet partiel qui sera deep-merge dans le JSON actuel.
- Pour modifier brand.title : {{"brand": {{"title": "..."}}}}
- Pour changer le theme : {{"theme": "medical-mint"}}
- Pour modifier hero.tagline : {{"hero": {{"tagline": "..."}}}}
- Pour remplacer COMPLETEMENT un tableau (ex faq.items), donne le tableau complet (pas juste 1 item).
- Pour ajouter une FAQ, donne le tableau faq.items complet (avec les anciennes + la nouvelle).

Si la demande est ambigue ou impossible, mets "patch": null et explique."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": req.message}],
    )

    raw = msg.content[0].text.strip()
    # Try to find a JSON object in the response
    response = None
    try:
        # Strip markdown fences if present
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        response = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback : extract first {...} block
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                response = json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass

    if not response:
        return {"explanation": raw, "patch": None, "applied": False}

    applied = False
    if req.apply and response.get("patch"):
        new_data = deep_merge(site_data, response["patch"])
        site_path.write_text(json.dumps(new_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(TE / "generate.py"), str(site_path)],
            check=True,
            capture_output=True,
        )
        applied = True

    return {
        "explanation": response.get("explanation", ""),
        "patch": response.get("patch"),
        "applied": applied,
    }


@app.post("/api/sites/{slug}/apply_patch")
def apply_patch(slug: str, body: dict):
    slug = _safe_slug(slug)
    site_path = SITES_DIR / f"{slug}.json"
    if not site_path.exists():
        raise HTTPException(404)
    patch = body.get("patch")
    if not patch:
        raise HTTPException(400, "patch manquant")
    site_data = json.loads(site_path.read_text(encoding="utf-8"))
    new_data = deep_merge(site_data, patch)
    site_path.write_text(json.dumps(new_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    subprocess.run(
        [sys.executable, str(TE / "generate.py"), str(site_path)],
        check=True,
        capture_output=True,
    )
    return {"ok": True}


# --- Planity import ---


class PlanityImportRequest(BaseModel):
    url: str
    slug: str | None = None
    theme: str = "esthetique-rose"


@app.post("/api/import/planity")
def import_planity(req: PlanityImportRequest):
    """Scrape a Planity URL and create a new site.json from it."""
    url = req.url.strip()
    if not url.startswith(("http://", "https://")) or "planity.com" not in url:
        raise HTTPException(400, "URL Planity invalide (doit contenir planity.com)")

    # Step 1 : run scraper (planity_scraper.py) — writes to a temp file
    scraper = ROOT / "planity_scraper.py"
    if not scraper.exists():
        raise HTTPException(500, "planity_scraper.py introuvable a la racine du projet")

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        planity_json = Path(tmpdir) / "planity.json"
        # Inline call : we import the function directly to avoid double-Playwright launch
        try:
            sys.path.insert(0, str(ROOT))
            from planity_scraper import scrape_planity
            data = scrape_planity(url, debug=False)
        except ImportError as e:
            raise HTTPException(500, f"Playwright manquant ? Installe avec : pip3 install playwright && python3 -m playwright install chromium. Erreur : {e}")
        except Exception as e:
            raise HTTPException(500, f"Erreur scrape : {e}")
        finally:
            if str(ROOT) in sys.path:
                sys.path.remove(str(ROOT))

        if not data:
            raise HTTPException(500, "Le scraper n'a rien retourne (page bloquee, cookies, ou structure changee)")

        planity_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Step 2 : map planity.json -> site.json
        sys.path.insert(0, str(TE))
        try:
            from planity_to_site import planity_to_site, slugify
        finally:
            if str(TE) in sys.path:
                sys.path.remove(str(TE))

        slug = req.slug or slugify(data.get("nom", "site"))
        slug = _safe_slug(slug)
        site = planity_to_site(data, slug, theme=req.theme)

        # Step 3 : save and generate HTML
        site_path = SITES_DIR / f"{slug}.json"
        site_path.write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(TE / "generate.py"), str(site_path)],
            check=True,
            capture_output=True,
        )

    return {
        "ok": True,
        "slug": slug,
        "name": site["brand"]["name"],
        "n_services": sum(len(f["items"]) for f in site["services"]["families"]),
        "n_families": len(site["services"]["families"]),
    }


# --- Netlify deploy ---


class DeployRequest(BaseModel):
    site_id: str | None = None  # if known, redeploy to same Netlify site


# Persisted map slug -> netlify site_id (so redeploys reuse the same URL)
_NETLIFY_MAP = TE / "netlify_sites.json"


def _load_netlify_map() -> dict:
    if _NETLIFY_MAP.exists():
        return json.loads(_NETLIFY_MAP.read_text(encoding="utf-8"))
    return {}


def _save_netlify_map(m: dict):
    _NETLIFY_MAP.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@app.post("/api/sites/{slug}/deploy")
def deploy_site(slug: str):
    """Deploy the generated site to Netlify via API. Reuses existing Netlify site if present."""
    slug = _safe_slug(slug)
    token = os.environ.get("NETLIFY_TOKEN", "").strip()
    if not token:
        raise HTTPException(400, "NETLIFY_TOKEN manquant dans dashboard/.env")

    # Ensure freshly generated
    site_json = SITES_DIR / f"{slug}.json"
    if not site_json.exists():
        raise HTTPException(404, "Site inconnu")
    subprocess.run(
        [sys.executable, str(TE / "generate.py"), str(site_json)],
        check=True,
        capture_output=True,
    )

    out_dir = OUT_DIR / slug
    if not (out_dir / "index.html").exists():
        raise HTTPException(500, "HTML non genere")

    # Copy assets from docs/{slug}/assets if present
    assets_src = DOCS_DIR / slug / "assets"
    assets_dst = out_dir / "assets"
    if assets_src.exists() and not assets_dst.exists():
        import shutil
        shutil.copytree(assets_src, assets_dst)

    # Zip the output folder
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in out_dir.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(out_dir))
    zip_bytes = buf.getvalue()

    import urllib.request
    headers = {"Authorization": f"Bearer {token}"}
    nmap = _load_netlify_map()
    site_id = nmap.get(slug)

    # Create site if needed
    if not site_id:
        body = json.dumps({"name": f"{slug}-preview"}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.netlify.com/api/v1/sites",
            data=body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            raise HTTPException(e.code, f"Netlify create error : {err}")
        site_id = resp["id"]
        nmap[slug] = site_id
        _save_netlify_map(nmap)

    # Deploy ZIP
    deploy_url = f"https://api.netlify.com/api/v1/sites/{site_id}/deploys"
    req = urllib.request.Request(
        deploy_url,
        data=zip_bytes,
        headers={**headers, "Content-Type": "application/zip"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            deploy = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(e.code, f"Netlify deploy error : {err}")

    url = deploy.get("ssl_url") or deploy.get("url") or ""
    return {
        "ok": True,
        "slug": slug,
        "site_id": site_id,
        "url": url,
        "state": deploy.get("state"),
    }


# --- Lead Finder (Prospection) ---


@app.get("/api/leads/metiers")
def leads_metiers():
    sys.path.insert(0, str(TE))
    try:
        from lead_finder_api import list_metiers
        return {"metiers": list_metiers()}
    finally:
        if str(TE) in sys.path:
            sys.path.remove(str(TE))


@app.get("/api/leads/villes")
def leads_villes():
    sys.path.insert(0, str(TE))
    try:
        from lead_finder_api import list_villes
        return {"villes": list_villes()}
    finally:
        if str(TE) in sys.path:
            sys.path.remove(str(TE))


@app.get("/api/leads/search")
def leads_search(city: str, metier: str, limit: int = 20, only_opportunities: bool = True):
    sys.path.insert(0, str(TE))
    try:
        from lead_finder_api import search_leads
        result = search_leads(city, metier, limit=limit, only_opportunities=only_opportunities)
        return result
    finally:
        if str(TE) in sys.path:
            sys.path.remove(str(TE))


class GenerateFromLeadRequest(BaseModel):
    nom: str
    metier: str
    ville: str
    adresse: str = ""
    telephone: str = ""
    website: str = ""
    planity_url: str = ""
    instagram: str = ""
    theme: str = "esthetique-rose"


@app.post("/api/leads/generate")
def generate_from_lead(req: GenerateFromLeadRequest):
    """Generate a site.json from a lead found via search.

    - If planity_url is set, scrape Planity + map to site.json (full data)
    - Otherwise, create a skeleton site.json with the basic info from OSM
    """
    sys.path.insert(0, str(TE))
    try:
        from planity_to_site import planity_to_site, slugify
    finally:
        if str(TE) in sys.path:
            sys.path.remove(str(TE))

    slug = slugify(req.nom)
    slug = _safe_slug(slug)

    # If we have a Planity URL : scrape it for full data
    if req.planity_url and "planity.com" in req.planity_url:
        sys.path.insert(0, str(ROOT))
        try:
            from planity_scraper import scrape_planity
            data = scrape_planity(req.planity_url, debug=False)
        except Exception as e:
            data = None
        finally:
            if str(ROOT) in sys.path:
                sys.path.remove(str(ROOT))
        if data:
            site = planity_to_site(data, slug, theme=req.theme)
        else:
            site = _skeleton_site(req, slug)
    else:
        site = _skeleton_site(req, slug)

    site_path = SITES_DIR / f"{slug}.json"
    site_path.write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    subprocess.run(
        [sys.executable, str(TE / "generate.py"), str(site_path)],
        check=True,
        capture_output=True,
    )
    return {
        "ok": True,
        "slug": slug,
        "name": site["brand"]["name"],
        "has_planity_data": bool(req.planity_url and "planity.com" in req.planity_url),
    }


def _skeleton_site(req: GenerateFromLeadRequest, slug: str) -> dict:
    """Build a skeleton site.json from a lead's basic info."""
    nom = req.nom
    ville = req.ville
    insta_handle = (req.instagram or f"@{slug.replace('-', '_')}").lstrip("@").rstrip("/")
    if "instagram.com/" in insta_handle:
        insta_handle = insta_handle.split("instagram.com/")[-1].rstrip("/")
    return {
        "slug": slug,
        "theme": req.theme,
        "brand": {
            "name": nom,
            "name_html": _name_html(nom),
            "title": f"{nom}, {ville}",
            "meta_description": f"{nom} à {ville}.",
            "og_title": f"{nom}, {ville}",
            "og_description": f"{nom}. {ville}.",
            "og_image": "assets/post_004.jpg",
            "favicon": "assets/profil.jpg",
            "footer_description": f"{nom}. {ville}.",
            "copyright_name": nom,
        },
        "nav": [
            {"label": "L'approche", "href": "#approche"},
            {"label": "Soins", "href": "#protocoles"},
            {"label": "Questions", "href": "#questions"},
            {"label": "Contact", "href": "#contact"},
        ],
        "cta_primary": {
            "label_long": "Prendre rendez-vous",
            "label_short": "RDV",
            "url": req.planity_url or req.website or f"https://www.instagram.com/{insta_handle}/",
        },
        "hero": {
            "eyebrow_num": "01",
            "eyebrow_text": ville,
            "h1_html": f"<em class=\"acc\">{nom}.</em>",
            "tagline": f"[A REDIGER] Description de {nom} a {ville}.",
            "ctas": [
                {"label": "Prendre rendez-vous", "url": req.planity_url or f"https://www.instagram.com/{insta_handle}/", "style": "primary", "external": True},
                {"label": "Voir les soins", "url": "#protocoles", "style": "light"},
            ],
            "image": {"src": "assets/post_004.jpg", "alt": nom, "caption": ville},
        },
        "marquee": {"tags": ["Prestations", "Soins", "Bien-etre"]},
        "about": {
            "id": "approche",
            "eyebrow_num": "02",
            "eyebrow_text": "L'approche",
            "h2_html": "Bienvenue.",
            "signature": f"{nom}. {ville}.",
            "paragraphs": [
                f"[A REDIGER] Presentation de {nom} a {ville}.",
                "[A REDIGER] Approche, savoir-faire, ambiance.",
            ],
        },
        "services": {
            "id": "protocoles",
            "eyebrow_num": "03",
            "eyebrow_text": "Les soins",
            "h2_html": "Le catalogue,<br>en détail.",
            "intro": "[A REDIGER] Liste des prestations.",
            "families": [{"name": "Prestations", "items": []}],
        },
        "faq": {
            "id": "questions",
            "eyebrow_num": "05",
            "eyebrow_text": "Questions",
            "h2_html": "Les questions<br>qui reviennent.",
            "items": [
                {"q": "Comment réserver ?", "a": "[A REDIGER]"},
                {"q": "Où se trouve l'institut ?", "a": req.adresse or f"À {ville}."},
            ],
        },
        "contact": {
            "id": "contact",
            "eyebrow_num": "06",
            "eyebrow_text": "Contact",
            "h2_html": "Prendre rendez-vous.",
            "intro": "[A REDIGER] Modalites de reservation.",
            "cards": _skeleton_contact_cards(req),
        },
        "footer": {
            "coords": [
                {"label": f"@{insta_handle}", "url": f"https://www.instagram.com/{insta_handle}/", "external": True},
            ],
        },
    }


def _name_html(name: str) -> str:
    parts = name.split(" ", 1)
    if len(parts) == 2:
        return f"{parts[0]} <em>{parts[1]}</em>"
    return name


def _skeleton_contact_cards(req: GenerateFromLeadRequest) -> list:
    cards = []
    if req.planity_url:
        cards.append({"lbl": "Réserver en ligne", "val_html": f'<a href="{req.planity_url}" target="_blank">Sur Planity ↗</a>'})
    if req.telephone:
        cards.append({"lbl": "Téléphone", "val_html": req.telephone.replace(" ", "&nbsp;")})
    if req.adresse:
        cards.append({"lbl": "Adresse", "val_html": req.adresse.replace(", ", ",<br>")})
    if not cards:
        cards.append({"lbl": "Contact", "val_html": "[A REDIGER]"})
    return cards


@app.get("/api/sites/{slug}/netlify")
def get_netlify_info(slug: str):
    slug = _safe_slug(slug)
    nmap = _load_netlify_map()
    site_id = nmap.get(slug)
    if not site_id:
        return {"deployed": False}
    return {
        "deployed": True,
        "site_id": site_id,
        "url": f"https://{slug}-preview.netlify.app",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
