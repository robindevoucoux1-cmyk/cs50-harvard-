"""Scrape les avis Google Maps pour un lead, via Playwright.

Strategie :
1. Cherche le nom commercial + ville sur Google Maps via une URL de search
2. Ouvre la fiche du 1er resultat
3. Clique sur l'onglet "Avis"
4. Recupere les N avis triés "Plus utiles" (= les meilleurs en general)
5. Sauve dans dossier_site/google_reviews.json

Cout : $0 (gratuit, juste Playwright local).
Latence : ~15-25s par lead.

Limites :
- Google peut presenter une page consent cookies au premier load. Geree.
- Si le commerce n'a pas de fiche Google ou pas d'avis, retourne None.
- Pas garanti que la fiche trouvee soit bien celle du lead (homonymes). On
  filtre en exigeant que le nom de la fiche contienne au moins 50% des mots
  du nom commercial recherche.
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]
    PWTimeout = Exception


def _normalise(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _meme_marque(nom_recherche: str, nom_fiche: str) -> bool:
    """Verifie qu'au moins 50% des mots du nom recherche sont dans la fiche."""
    mots_r = set(_normalise(nom_recherche).split())
    mots_f = set(_normalise(nom_fiche).split())
    if not mots_r:
        return True
    mots_communs = mots_r & mots_f
    return len(mots_communs) / len(mots_r) >= 0.5


def _accepte_cookies(page):
    """Tente de cliquer sur "Tout refuser" ou "Tout accepter" sur la page consent."""
    for selecteur in [
        'button:has-text("Tout refuser")',
        'button:has-text("Reject all")',
        'button[aria-label*="Tout refuser"]',
        'button:has-text("Tout accepter")',
        'button:has-text("Accept all")',
    ]:
        try:
            btn = page.query_selector(selecteur)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(800)
                return
        except Exception:
            pass


def scrape_avis(nom_commercial: str, ville: str, max_avis: int = 6, debug: bool = False) -> dict | None:
    """Cherche le commerce sur Google Maps et recupere ses avis.

    Renvoie un dict :
        {
            "trouve": bool,
            "nom_fiche": str,
            "note_moyenne": float,
            "nb_avis_total": int,
            "url_maps": str,
            "avis": [{"auteur": str, "note": int, "texte": str, "date_relative": str}, ...]
        }
    """
    if sync_playwright is None:
        raise RuntimeError("playwright non installe.")

    requete = f"{nom_commercial} {ville}"
    url = f"https://www.google.com/maps/search/{quote_plus(requete)}/?hl=fr"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="fr-FR",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            ignore_https_errors=True,
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1500)
            _accepte_cookies(page)
            page.wait_for_timeout(1500)

            # Apres consent, on peut etre soit sur :
            # a) page de resultats Maps avec liste a gauche
            # b) directement la fiche d'un commerce (resultat unique)
            # c) page d'erreur / aucun resultat

            # Cas a : on doit cliquer sur le 1er resultat dans le panneau de gauche
            try:
                page.wait_for_selector('div[role="feed"], div[role="main"]', timeout=8000)
            except PWTimeout:
                pass

            # Cherche les liens de resultats dans le feed
            premier_resultat = page.query_selector('a[href*="/maps/place/"]')
            if premier_resultat:
                # Verifie le nom du resultat avant de cliquer
                nom_resultat = premier_resultat.get_attribute("aria-label") or ""
                if nom_resultat and not _meme_marque(nom_commercial, nom_resultat):
                    if debug:
                        print(f"    [reviews] 1er resultat '{nom_resultat}' ne match pas '{nom_commercial}'")
                premier_resultat.click()
                page.wait_for_timeout(2500)

            # Maintenant on devrait etre sur une fiche commerce.
            # Recupere le nom de la fiche
            h1 = page.query_selector('h1.DUwDvf, h1[class*="fontHeadlineLarge"]')
            nom_fiche = h1.inner_text() if h1 else ""

            if not nom_fiche:
                if debug:
                    print(f"    [reviews] Pas de fiche trouvee pour {requete}")
                return {"trouve": False, "raison": "pas de fiche"}

            if not _meme_marque(nom_commercial, nom_fiche):
                if debug:
                    print(f"    [reviews] Fiche trouvee '{nom_fiche}' ne match pas '{nom_commercial}'")
                return {"trouve": False, "raison": "match faible", "nom_fiche": nom_fiche}

            url_maps = page.url

            # Note moyenne + nb avis total : dans le header de la fiche
            note_moyenne = None
            nb_avis_total = 0
            try:
                note_el = page.query_selector('div.F7nice span[aria-hidden="true"]')
                if note_el:
                    note_str = note_el.inner_text().replace(",", ".").strip()
                    note_moyenne = float(re.match(r"[\d.]+", note_str).group())
                nb_avis_el = page.query_selector('div.F7nice span[aria-label*="avis"]')
                if nb_avis_el:
                    txt = nb_avis_el.get_attribute("aria-label") or ""
                    m = re.search(r"(\d+[\s\d]*)\s*avis", txt)
                    if m:
                        nb_avis_total = int(m.group(1).replace(" ", ""))
            except Exception:
                pass

            # Clique sur l'onglet "Avis"
            avis = []
            tab_clique = False
            for sel in [
                'button[aria-label^="Avis "]',
                'button[aria-label*="avis sur"]',
                'button[role="tab"][aria-label*="Avis"]',
                'button[jsaction*="reviewTab"]',
                'button:has-text("Avis")',
            ]:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(2500)
                        tab_clique = True
                        if debug:
                            print(f"    [reviews] click tab avis via {sel}")
                        break
                except Exception:
                    continue

            # Scroll dans le panneau pour charger plus d'avis (lazy load)
            try:
                panel = page.query_selector('div[role="main"], div.m6QErb[aria-label]')
                if panel:
                    for _ in range(3):
                        page.evaluate("(el) => el.scrollBy(0, 800)", panel)
                        page.wait_for_timeout(800)
            except Exception:
                pass

            # Recupere les blocs avis : essaie plusieurs strategies
            blocs = page.query_selector_all('div[data-review-id]')
            if not blocs:
                blocs = page.query_selector_all('div.jftiEf')
            if debug:
                print(f"    [reviews] {len(blocs)} blocs avis trouves")

            for bloc in blocs[: max_avis * 3]:
                try:
                    plus_btn = bloc.query_selector('button:has-text("Plus"), button[aria-label*="Plus"]')
                    if plus_btn and plus_btn.is_visible():
                        plus_btn.click()
                        page.wait_for_timeout(120)

                    # Auteur : plusieurs selecteurs
                    auteur = ""
                    for s in ['div.d4r55', 'div.TSUbDb', '.WNxzHc']:
                        el = bloc.query_selector(s)
                        if el:
                            auteur = el.inner_text().strip()
                            if auteur:
                                break

                    # Note : aria-label avec etoile
                    note = 0
                    for s in ['span[role="img"][aria-label*="oile"]', 'span.kvMYJc', '[aria-label*="oile"]']:
                        el = bloc.query_selector(s)
                        if el:
                            lbl = el.get_attribute("aria-label") or ""
                            m = re.search(r"(\d+)", lbl)
                            if m:
                                note = int(m.group(1))
                                break

                    # Texte : plusieurs selecteurs
                    texte = ""
                    for s in ['span.wiI7pd', 'span[class*="MyEned"]', 'div.MyEned', '.review-full-text']:
                        el = bloc.query_selector(s)
                        if el:
                            texte = el.inner_text().strip()
                            if texte:
                                break

                    # Date
                    date_rel = ""
                    for s in ['span.rsqaWe', 'span.DU9Pgb', 'span[class*="rsqaWe"]']:
                        el = bloc.query_selector(s)
                        if el:
                            date_rel = el.inner_text().strip()
                            if date_rel:
                                break

                    if texte and len(texte) > 10 and 1 <= note <= 5:
                        avis.append({
                            "auteur": auteur or "Client",
                            "note": note,
                            "texte": texte,
                            "date_relative": date_rel,
                        })
                    if len(avis) >= max_avis:
                        break
                except Exception:
                    continue

            # Adresse / telephone / horaires depuis le panneau info de la fiche
            adresse = ""
            telephone = ""
            site_web = ""
            for sel in [
                'button[data-item-id="address"]',
                'button[aria-label*="Adresse"]',
                'div[data-item-id="address"]',
            ]:
                el = page.query_selector(sel)
                if el:
                    txt = (el.get_attribute("aria-label") or el.inner_text() or "").replace("Adresse:", "").strip()
                    if txt:
                        adresse = txt
                        break
            for sel in [
                'button[data-item-id^="phone"]',
                'button[aria-label*="Numéro"]',
                'button[aria-label*="Téléphone"]',
            ]:
                el = page.query_selector(sel)
                if el:
                    txt = (el.get_attribute("aria-label") or el.inner_text() or "").replace("Numéro de téléphone:", "").strip()
                    if txt:
                        telephone = txt
                        break
            for sel in [
                'a[data-item-id="authority"]',
                'a[aria-label*="Site Web"]',
                'a[data-tooltip*="site Web"]',
            ]:
                el = page.query_selector(sel)
                if el:
                    txt = el.get_attribute("href") or el.inner_text()
                    if txt and "http" in txt:
                        site_web = txt
                        break

            return {
                "trouve": True,
                "nom_fiche": nom_fiche,
                "note_moyenne": note_moyenne,
                "nb_avis_total": nb_avis_total,
                "url_maps": url_maps,
                "adresse": adresse,
                "telephone": telephone,
                "site_web": site_web,
                "avis": avis,
            }

        except PWTimeout as e:
            if debug:
                print(f"    [reviews] timeout : {e}")
            return None
        finally:
            browser.close()


def scrape_pour_lead(dossier_site: Path, ville: str, max_avis: int = 6) -> dict | None:
    """Lit metadata.json et scrape les avis Google. Sauve google_reviews.json."""
    meta_path = dossier_site / "metadata.json"
    if not meta_path.exists():
        print(f"  [reviews-error] metadata.json absent dans {dossier_site}")
        return None
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    # Essaie d'abord avec le nom_commercial du brief si dispo, sinon fullName
    brief_path = dossier_site / "brand_and_copy.json"
    nom = ""
    if brief_path.exists():
        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        nom = brief.get("nom_commercial") or ""
    if not nom:
        nom = metadata.get("fullName") or metadata.get("handle", "")
    # Nettoyage : enleve emojis, separateurs |, etc.
    nom_propre = re.sub(r"[|••\-—]+", " ", nom)
    nom_propre = re.sub(r"[^\w\sàâéèêëîïôûùç&\']", " ", nom_propre, flags=re.IGNORECASE)
    nom_propre = re.sub(r"\s+", " ", nom_propre).strip()
    # Tronque a 4 mots max pour eviter une requete trop longue (Google preferera
    # un match partiel pertinent qu'une chaine longue qui ne match rien).
    # On exclut les mots generiques metier qui polluent.
    STOP_METIER = {"estheticienne", "estheticien", "esthetique", "prothesiste", "ongulaire",
                   "specialiste", "professionnelle", "professionnel", "expert", "experte"}
    mots = [m for m in nom_propre.split() if m.lower() not in STOP_METIER]
    nom_propre = " ".join(mots[:4]) if mots else nom_propre

    print(f"  [reviews] recherche '{nom_propre}' a {ville}...")
    t0 = time.time()
    result = scrape_avis(nom_propre, ville, max_avis=max_avis, debug=True)
    duree = time.time() - t0

    if not result or not result.get("trouve"):
        raison = (result or {}).get("raison", "non trouve")
        print(f"  [reviews] pas d'avis recuperes ({raison}) en {duree:.0f}s")
        # On sauve quand meme pour ne pas re-essayer a chaque run
        result = {"trouve": False, "raison": raison, "nom_recherche": nom_propre}
    else:
        print(f"  [reviews] {len(result['avis'])} avis recuperes (note {result.get('note_moyenne','?')}/5, {result.get('nb_avis_total','?')} avis au total) en {duree:.0f}s")

    chemin = dossier_site / "google_reviews.json"
    chemin.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python google_reviews.py <dossier_site> <ville> [<max_avis>]")
        return 1
    dossier = Path(sys.argv[1])
    ville = sys.argv[2]
    max_avis = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    result = scrape_pour_lead(dossier, ville, max_avis)
    if not result:
        return 1
    if result.get("trouve"):
        print(f"\nFiche : {result['nom_fiche']}")
        print(f"Note  : {result.get('note_moyenne','?')}/5  ({result.get('nb_avis_total','?')} avis)")
        for a in result.get("avis", []):
            print(f"\n  [{a['note']}/5] {a['auteur']} ({a['date_relative']})")
            print(f"  {a['texte'][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
