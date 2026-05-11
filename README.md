# Lead Finder & Site Generator

Pipeline complet qui transforme un metier + une ville en sites web preview
personnalises a partir des Instagram des commercants locaux qui investissent
dans leur com mais n'ont pas encore de site.

```
metier + ville  ->  Apify  ->  leads qualifies (CSV)
       |
       v
   Pour chaque lead :
   - scrape 12-30 posts (Apify)
   - Claude Vision : selection des 9 meilleures photos
   - Claude Sonnet : palette + ton + copy adapte a la marque
   - Jinja2 : template HTML responsive personnalise
       |
       v
   output/sites/<slug>/index.html (deployable Netlify/Vercel)
```

## Installation

```bash
pip install -r requirements.txt
python -m playwright install chromium  # pour les screenshots preview
cp .env.example .env   # puis edite avec tes 2 cles API
```

Deux cles API requises :
- `APIFY_TOKEN` : https://console.apify.com/account/integrations ($5/mois gratuit)
- `ANTHROPIC_API_KEY` : https://console.anthropic.com/settings/keys ($5 gratuit a l'inscription)

## Pipeline complet

### Etape 1 : trouver les prospects qualifies

```bash
python insta_first_finder.py --metier "esthéticienne" --ville "Bordeaux" \
    --limit 30 --min-followers 500
```

Sortie : `output/leads_<metier>_<ville>.csv` avec les comptes qui ont :
- followers >= seuil (defaut 500)
- la ville dans bio/handle/categorie
- le metier coherent
- pas de vrai site web (Planity/Linktree autorises, vrai site exclu)

Cout : ~$0.02 par recherche, donne 5-15 leads qualifies.

### Etape 2 : generer les sites preview

```bash
# Pour tous les leads du CSV :
python generate_site.py --csv output/leads_esthéticienne_bordeaux.csv

# Pour un seul handle :
python generate_site.py --handle institut_beauty_bar \
    --metier "esthéticienne" --ville "Bordeaux"

# Limite a N leads :
python generate_site.py --csv <csv> --limit 3
```

Sortie pour chaque lead dans `output/sites/<slug>/` :
- `index.html` : le site complet (autoportant, deployable)
- `assets/` : photo de profil + 12 photos d'origine
- `metadata.json` : donnees scrapees brutes
- `photo_selection.json` : analyse Vision de chaque photo + selection
- `brand_and_copy.json` : palette, typo, ton, copy

**Cout total par site : ~$0.11**
- Apify scrape : $0.07
- Claude Vision : $0.02
- Claude Sonnet : $0.025

### Etape 3 : visualiser les sites

```bash
cd output/sites
python -m http.server 8000
# puis ouvrir http://127.0.0.1:8000/<slug>/ dans ton navigateur
```

## Modules

| Module | Role | Cout/lead |
|---|---|---|
| `lead_finder.py` | Source OSM (sans Insta) - cible originale | $0 |
| `competitor_analyzer.py` | Analyse des concurrents avec site | $0 |
| `apify_scraper.py` | Helpers Apify (search + scrape) | - |
| `insta_first_finder.py` | **Cible** : leads Insta qualifies, sans site | ~$0.003 |
| `scrape_riche.py` | Rescrape complet + telechargement images | ~$0.07 |
| `photo_curator.py` | Claude Vision : selection des 9 meilleures photos | ~$0.02 |
| `brand_and_copy.py` | Claude Sonnet : palette + ton + copy site | ~$0.025 |
| `site_builder.py` | Jinja2 : assemble le site HTML final | $0 |
| `generate_site.py` | Orchestrateur (chaine les 4 etapes) | $0.11 (somme) |
| `prospect_enricher.py` | Pipeline alternatif OSM-first (legacy) | $0.015 |

## Personnalisation des templates

Les 3 familles de templates sont definies dans `brand_and_copy.py` (constante
`CODES_SECTEUR`). Chacune a sa palette suggeree, sa typographie, son mood,
ses sections et ses CTA types :

- **beaute** : esthéticienne, onglerie, lash, soin visage
- **wellness** : sophrologue, naturopathe, yoga
- **sport** : coach sportif, fitness, personal trainer

Pour ajouter un metier : ajoute une entree dans `CODES_SECTEUR`.

Pour modifier le rendu visuel : edite `templates/site.html.j2`. Les couleurs
et les fonts sont injectees via CSS variables (`--primaire`, `--secondaire`,
`--font-titre`, `--font-texte`).

## Limites connues

- Apify Instagram search retourne max 10-15 resultats par requete. Pour scaler
  a 100+ leads par ville, diversifier les requetes (variantes nom-metier,
  villes voisines de la metropole, etc.).
- Apify Instagram scraper retourne souvent 12 posts max (limite plateforme).
- Pas encore de templates speciaux pour les comptes < 500 followers ou
  comptes prives.
- Les CSS variables modernes (`color-mix()`) requierent un navigateur
  recent (Safari 16.4+, Chrome 111+).

## Cibles recommandees (donnees marche France 2024)

Le pipeline cible par defaut les professions "bien-etre + esthetique" :
- Estheticiennes / instituts de beaute (65 000 etablissements)
- Sophrologues (20 800 +1 500/an)
- Naturopathes (6 000, marche 400M EUR)
- Coachs sportifs independants (25 000)

Verticales evitees : restaurants (78% deja digitalises), coiffeurs (sature),
photographes mariage (1 pour 8 mariages), avocats/medecins (encadrement strict).
