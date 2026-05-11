# Lead Finder & Site Generator

Pipeline complet pour prospecter et generer des sites web :
1. **Trouver** des commerces sans site internet (gratuit, via OpenStreetMap)
2. **Analyser** la concurrence locale (gratuit)
3. **Enrichir** chaque prospect avec ses donnees Instagram (Apify recommande)
4. *(a venir)* **Generer** un site preview personnalise par prospect
5. *(a venir)* **Deployer** et **notifier** sur Telegram pour validation

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env  # puis edite .env avec ton APIFY_TOKEN
```

## Etape 1 : trouver les prospects

```bash
# Tous les metiers x toutes les villes du config.py
python lead_finder.py

# Une ville + un metier
python lead_finder.py --ville Bordeaux --metier esthéticienne
```

Sortie : `output/prospects.csv` avec nom, telephone, adresse, lien Maps, etc.

## Etape 2 : analyser la concurrence

```bash
python competitor_analyzer.py --ville Bordeaux --metier esthéticienne --max 15
```

Sortie : un rapport JSON + Markdown listant pages communes, CTA, couleurs, polices des concurrents qui ont un site. Sert de baseline pour generer les futurs sites.

## Etape 3 : enrichir les prospects avec Instagram

### Option A : Apify (recommande)

Pourquoi : pas de risque de ban, donnees structurees, fiable. Tarif reel : ~$0.005 par prospect, et la free tier Apify offre $5/mois (~1 000 prospects gratuits).

1. Creer un compte Apify : https://console.apify.com/sign-up
2. Recuperer le token : https://console.apify.com/account/integrations
3. Mettre `APIFY_TOKEN=...` dans `.env`

```bash
python prospect_enricher.py --input output/prospects.csv --backend apify --limit 20
```

### Option B : instaloader (gratuit mais limite)

```bash
python prospect_enricher.py --input output/prospects.csv --backend instaloader --limit 20
```

Limite : ~30-50 prospects/jour sans login avant blocage Instagram.

### Sortie

- `output/prospects_enriched.csv` : chaque prospect avec ses colonnes Insta (handle, followers, bio, categorie)
- `output/profils/{nom}.json` : profil detaille de chaque prospect (bio complete, 6 derniers posts avec captions et URL photos)

Ce JSON par prospect est la matiere premiere pour generer les sites a l'etape suivante.

## Cibles recommandees (donnees marche France 2024)

Le `config.py` cible par defaut les professions "bien-etre + esthetique" :
- Estheticiennes / instituts de beaute (65 000 etablissements, +17 500 ouvertures en 2024)
- Sophrologues (20 800, +1 500/an)
- Naturopathes (6 000, marche 400M€)
- Coachs sportifs independants (25 000)
- Salles de sport / yoga
- Osteopathes (cibles secondaires)

Verticales evitees : restaurants (78% deja digitalises), coiffeurs (sature), photographes mariage (1 pour 8 mariages), avocats/medecins (encadrement strict).
