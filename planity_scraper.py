"""Scrape une fiche Planity et recupere les vraies donnees du commerce :
- Nom officiel
- Adresse
- Telephone
- Categorie
- Services (nom + duree + prix)
- Avis (note moyenne + textes)

Sortie : planity.json dans le dossier du site.
"""

import json
import re
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]
    PWTimeout = Exception


def scrape_planity(url: str, debug: bool = False) -> dict | None:
    if sync_playwright is None:
        raise RuntimeError("playwright non installe.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--ignore-certificate-errors"],
        )
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="fr-FR",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            ignore_https_errors=True,
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Cookies banner
            for sel in [
                'button:has-text("Tout accepter")',
                'button:has-text("Accepter")',
                'button[id*="accept"]',
                'button[class*="accept"]',
            ]:
                try:
                    b = page.query_selector(sel)
                    if b and b.is_visible():
                        b.click()
                        page.wait_for_timeout(500)
                        if debug:
                            print(f"    [planity] cookies OK via {sel}")
                        break
                except Exception:
                    pass

            # Scroll un peu pour charger les sections lazy
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(800)

            result = {"url": url}

            # Nom : h1 principal
            for sel in ['h1', 'h1[class*="title"]', '[class*="business-name"]']:
                el = page.query_selector(sel)
                if el:
                    txt = el.inner_text().strip()
                    if txt and len(txt) < 120:
                        result["nom"] = txt
                        break

            # Adresse
            for sel in [
                '[class*="address"]',
                '[class*="Address"]',
                'address',
            ]:
                el = page.query_selector(sel)
                if el:
                    txt = el.inner_text().strip()
                    if txt and any(c.isdigit() for c in txt):
                        result["adresse"] = " ".join(txt.split())
                        break

            # Telephone
            tel_el = page.query_selector('a[href^="tel:"]')
            if tel_el:
                href = tel_el.get_attribute("href") or ""
                result["telephone"] = href.replace("tel:", "").strip()

            # Note moyenne + nb avis
            try:
                # Planity affiche genre "4.9 (123 avis)"
                rating_el = page.query_selector('[class*="rating"] strong, [class*="rating"] span, [class*="Rating"]')
                full_text = page.locator("body").inner_text()
                m = re.search(r"(\d[.,]\d)\s*\(?(\d+)\s*avis", full_text, re.IGNORECASE)
                if m:
                    result["note"] = float(m.group(1).replace(",", "."))
                    result["nb_avis"] = int(m.group(2))
            except Exception:
                pass

            # Services : Planity les liste avec nom + duree + prix
            # Format typique : "Pose semi-permanent · 60 min · 35 €"
            services = []
            # On cherche des blocs structurels qui contiennent des prix
            # Strategie : extraire tout le texte de la page, identifier patterns
            try:
                # Bloc menu/prestations
                bloc_text = page.locator('main, [class*="services"], [class*="prestations"]').first.inner_text()
            except Exception:
                bloc_text = page.locator("body").inner_text()

            # Pattern : "Nom du service\nXX min\nXX €" ou "Nom du service · XX min · XX €"
            # On parse ligne par ligne
            lignes = [l.strip() for l in bloc_text.split("\n") if l.strip()]
            i = 0
            while i < len(lignes):
                ligne = lignes[i]
                # Cherche un prix dans cette ligne ou la suivante
                m_prix = re.search(r"(\d+[,.]?\d*)\s*€", ligne)
                m_duree = re.search(r"(\d+)\s*(min|h(?:eure)?s?|min\.|m)\b", ligne, re.IGNORECASE)

                if m_prix and i > 0:
                    # Le nom du service est probablement dans une ligne precedente
                    nom_candidat = None
                    for k in range(1, 4):
                        if i - k >= 0:
                            cand = lignes[i - k]
                            if (
                                len(cand) > 4 and len(cand) < 100
                                and not re.search(r"€|min|^\d+$", cand, re.IGNORECASE)
                                and cand.lower() not in {"voir plus", "voir tout", "afficher plus", "réserver", "details", "détails"}
                            ):
                                nom_candidat = cand
                                break
                    if nom_candidat:
                        prix = m_prix.group(0)
                        duree = m_duree.group(0) if m_duree else ""
                        # eviter doublons
                        if not any(s["nom"] == nom_candidat for s in services):
                            services.append({"nom": nom_candidat, "duree": duree, "prix": prix})
                i += 1

            # Si rien trouvé via regex, on fait une recherche large
            if not services:
                items_dom = page.query_selector_all('[class*="service"], [class*="prestation"], [class*="treatment"], li')
                for item in items_dom[:60]:
                    try:
                        txt = item.inner_text().strip()
                        if "€" in txt and len(txt) < 220:
                            lines = [l.strip() for l in txt.split("\n") if l.strip()]
                            nom = lines[0] if lines else ""
                            prix_match = re.search(r"\d+[,.]?\d*\s*€", txt)
                            duree_match = re.search(r"\d+\s*(min|h(?:eure)?s?)", txt, re.IGNORECASE)
                            if nom and prix_match and len(nom) < 100:
                                if not any(s["nom"] == nom for s in services):
                                    services.append({
                                        "nom": nom,
                                        "duree": duree_match.group(0) if duree_match else "",
                                        "prix": prix_match.group(0),
                                    })
                    except Exception:
                        continue

            result["services"] = services[:30]
            result["nb_services_extraits"] = len(result["services"])

            return result

        except PWTimeout as e:
            if debug:
                print(f"    [planity] timeout : {e}")
            return None
        finally:
            browser.close()


def scrape_pour_lead(dossier_site: Path) -> dict | None:
    meta_path = dossier_site / "metadata.json"
    if not meta_path.exists():
        print(f"  [planity-error] metadata.json absent dans {dossier_site}")
        return None
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    url = metadata.get("externalUrl") or ""
    if "planity.com" not in url:
        print(f"  [planity] pas de fiche Planity pour ce lead (externalUrl: {url[:60]})")
        return None

    print(f"  [planity] scrape : {url}")
    result = scrape_planity(url, debug=True)
    if not result:
        return None

    chemin = dossier_site / "planity.json"
    chemin.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [planity] {result.get('nb_services_extraits', 0)} services extraits, sauve dans {chemin.name}")
    return result


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python planity_scraper.py <dossier_site>")
        print("   ou: python planity_scraper.py <url_planity>")
        return 1

    arg = sys.argv[1]
    if arg.startswith("http"):
        result = scrape_planity(arg, debug=True)
    else:
        result = scrape_pour_lead(Path(arg))

    if not result:
        return 1

    print()
    print(f"Nom         : {result.get('nom', '?')}")
    print(f"Adresse     : {result.get('adresse', '?')}")
    print(f"Tel         : {result.get('telephone', '?')}")
    print(f"Note        : {result.get('note', '?')}/5 ({result.get('nb_avis', '?')} avis)")
    print()
    print(f"Services    : {result.get('nb_services_extraits', 0)}")
    for s in result.get("services", []):
        nom = s.get("nom", "")
        duree = s.get("duree", "")
        prix = s.get("prix", "")
        print(f"  - {nom[:60]:<60} {duree:<12} {prix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
