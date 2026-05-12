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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
