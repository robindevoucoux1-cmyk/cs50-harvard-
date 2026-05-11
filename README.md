# Lead Finder — Commerces sans site web

Outil Python qui trouve des commerces **sans site internet** dans les villes francaises, via OpenStreetMap. **100% gratuit, sans cle API, sans carte bancaire.**

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

Tous les metiers dans toutes les villes (config.py) :
```bash
python lead_finder.py
```

Une ville + un metier precis :
```bash
python lead_finder.py --ville Lyon --metier osteopathe
```

Sortie personnalisee :
```bash
python lead_finder.py --output mes_leads.csv
```

## Sortie

CSV avec : nom, metier, ville, telephone, email, adresse, facebook, instagram, lien Google Maps, lien recherche Instagram.

## Personnaliser

Modifier `config.py` pour ajouter villes / metiers. Pour ajouter un metier, ajouter aussi son mapping OSM dans `METIER_TO_OSM` dans `lead_finder.py`.

## Limites

OpenStreetMap couvre ~30-60% des commerces selon la zone. Pour completer les telephones manquants, recherche manuelle Google Maps (lien fourni dans le CSV).
