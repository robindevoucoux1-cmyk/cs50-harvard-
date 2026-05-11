"""Configuration: cibles prioritaires pour la prospection.

Strategie : cibler les "professions du bien-etre" + esthetique, basee sur
les donnees du marche francais 2024 (sources dans le README) :
- Marche en croissance forte (medecines alternatives 2,5 Md€ -> 4 Md€ en 2027)
- Faible saturation par les agences web
- Decideurs uniques (solo praticiens) = vente rapide
- Insta-natifs = DM accessible

Note sur la couverture OSM :
- Instituts de beaute, salles de sport, salons : tres bonne couverture (vitrines).
- Sophrologues, naturopathes, coachs sportifs : couverture partielle (souvent
  domicile/cabinet partage non cartographies). Pour ces metiers, completer
  avec une recherche directe Instagram (hashtags geolocalises).
"""

VILLES = [
    "Paris",
    "Lyon",
    "Marseille",
    "Toulouse",
    "Bordeaux",
    "Nantes",
    "Lille",
    "Strasbourg",
    "Montpellier",
    "Rennes",
    "Nice",
    "Grenoble",
    "Toulon",
    "Angers",
    "Le Mans",
]

METIERS = [
    "esthéticienne",
    "salon de beauté",
    "salle de sport",
    "yoga studio",
    "naturopathe",
    "sophrologue",
    "coach sportif",
    "ostéopathe",
]

CATEGORIES_EXCLUES = {
    "car_dealer",
    "car_repair",
    "car_wash",
    "gas_station",
    "parking",
    "taxi_stand",
    "atm",
    "bank",
    "convenience_store",
    "supermarket",
}

NOTE_MINIMUM = 4.0
AVIS_MINIMUM = 10
