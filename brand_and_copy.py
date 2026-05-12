"""Analyse de marque + generation de copy pour le site, en 1 appel Sonnet.

Prend en input la bio, les photos curees (avec leur description IA), le metier
et la ville, et produit un JSON complet pret a etre injecte dans le template :

- brand_voice : ton, style, mots-cles d'identite
- palette : 3-4 couleurs hex coherentes avec les photos + le metier
- theme_template : nom du template a utiliser
- copy : tous les textes du site (h1, tagline, about, services, raisons,
  ctas, footer)
- meta : seo title + description

Cout estime : ~$0.12 par lead (Claude Sonnet 4.6, ~5k tokens output).
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]

MODELE_COPY = "claude-sonnet-4-6"


FAMILLE_PAR_METIER = {
    "esthéticienne": "beaute",
    "estheticienne": "beaute",
    "esthetique": "beaute",
    "onglerie": "beaute",
    "prothesiste": "beaute",
    "nail": "beaute",
    "coiffeur": "beaute",
    "barbier": "beaute",
    "coach sportif": "sport",
    "coach": "sport",
    "fitness": "sport",
    "personal trainer": "sport",
    "sophrologue": "wellness",
    "naturopathe": "wellness",
    "hypnotherapeute": "wellness",
    "yoga": "wellness",
    "osteopathe": "wellness",
}


SOUS_METIERS_REFERENCE = """SOUS-METIERS A IDENTIFIER (tu dois choisir le plus proche pour la marque
analysee). Pour chacun : palette ATTENDUE, codes visuels, leviers SONCAS dominants.

[ONGLERIE / NAIL ART / PROTHESISTE ONGULAIRE]
- Palette : bordeaux profond, rose poudre, nude, or rose, blanc casse, taupe.
  Couleur d'accent inspiree des manucures dominantes des photos.
- Typo titres : serif chic (Playfair Display, Cormorant Garamond)
- SONCAS dominants : Sympathie (proximite, "ma proth ongulaire"), Confort (cocon).
- Mood : feminin chic, salon de quartier, doux.
- CTAs : "Reserver mon RDV", "Prendre RDV", "Voir mes nail arts"

[LASH / EXTENSIONS CILS / SOURCILS]
- Palette : noir profond, or pale, nude, beige champagne, blanc.
- Typo titres : serif moderne ou sans serif elegant (Outfit Bold, DM Serif)
- SONCAS : Orgueil (regard de star), Sympathie.
- Mood : luxe accessible, glamour, feminin.

[EPILATION LASER / MEDICO-ESTHETIQUE]
- Palette : **BLEU clinique** (#1E3A5F, #4A8BC2), blanc pur (#FFFFFF), gris perle,
  vert eau clair (#E0F4F1), accent or rose tres discret OK. JAMAIS bordeaux/rouge.
- Typo titres : sans serif professionnel (Inter, Manrope, DM Sans)
- SONCAS dominants : **Securite** (rassurer sur le materiel/pratique),
  Argent (efficacite/duree), Confort (douceur du protocole).
- Mood : clinique professionnel, rassurance, expertise medicale, modernite.
- CTAs : "Prendre rendez-vous", "Bilan personnalise", "Premier diagnostic"

[SOINS PEAU / ANTI-AGE / SOINS VISAGE]
- Palette : beige sable, vert sauge tres doux, terracotta clair, blanc creme.
- Typo titres : serif elegante (Cormorant, Lora)
- SONCAS : Confort (rituel, plaisir), Nouveauté (actifs, technologie).
- Mood : cocooning, soin de soi, naturel pro.

[MASSAGE / SPA / RELAXATION]
- Palette : lin (#E8DFD3), ocre doux, vert sauge, terre cuite, blanc casse.
- Typo titres : serif douce, lettrage organique.
- SONCAS : Confort, Sympathie, Securite (relachement).
- Mood : zen, voyage interieur, rituel.

[MAQUILLAGE / MAKEUP ARTIST]
- Palette : nude, rose poudre, or, prune, marron chocolat, accents audacieux ok.
- Typo : serif glamour (Playfair) + sans serif graphique.
- SONCAS : Orgueil (se sentir belle), Sympathie.
- Mood : confiance en soi, art, evenementiel.

[SOPHROLOGUE / HYPNOSE / RELAXATION]
- Palette : vert sauge, bleu lavande pale, beige sable, ocre doux, lin.
  Aucune couleur vive.
- Typo titres : serif douce (Cormorant, Lora).
- SONCAS : Securite (confiance dans la pratique), Confort (lacher prise).
- Mood : calme, ecoute, instant present.

[NATUROPATHE / MEDECINE DOUCE]
- Palette : vert sauge, vert olive, terracotta, blanc creme, beige naturel.
- Typo : serif (Lora, Cormorant) + sans serif minimaliste.
- SONCAS : Securite (formation serieuse), Nouveauté (approche globale).
- Mood : nature, expertise douce, holistique.

[COACH SPORTIF]
- Palette : noir profond + accent orange vif OU jaune lime OU bleu electrique.
  Contraste fort.
- Typo titres : sans serif puissant (Anton, Bebas Neue, Inter Black).
- SONCAS : Orgueil (transformation), Argent (resultats rapides).
- Mood : energie, depassement, mental.

Si aucun ne colle, choisis 'autre' et propose palette/typo/SONCAS coherents
avec ce que tu vois sur les photos et la bio.
"""

SONCAS_REFERENCE = """SONCAS : grille de motivations d'achat des clients en BtoC France.
Tu dois detecter le levier dominant de la cible de la marque et adapter
H1, tagline, services et raisons en consequence.

- Securite : besoin d'etre rassure, eviter le risque. Mots-cles : protege,
  garanti, certifie, hygiene, materiel pro, controle, sans risque.
  Adapte pour : medico-esthetique, sophrologie, sante.
- Orgueil : prestige, image, se sentir unique. Mots-cles : exclusif, prestige,
  signature, sur-mesure, savoir-faire d'excellence, regard de star.
  Adapte pour : lash, makeup, coach premium, onglerie luxe.
- Nouveaute : decouverte, innovation, originalite. Mots-cles : nouveau,
  unique, signature, technologie, expert formee, methode exclusive.
  Adapte pour : tech esthetique, technique etrangere.
- Confort : facilite, gain de temps, plaisir. Mots-cles : cocon, douceur,
  bien-etre, rituel, simplicite, sans effort, moment pour soi.
  Adapte pour : spa, soins peau, sophrologue.
- Argent : economique, efficacite, ROI. Mots-cles : tarifs justes,
  forfait, gain de temps, resultat duraule, sans gachis.
  Adapte pour : prestations recurrentes, packages, abonnements.
- Sympathie : proximite, relation humaine, confiance. Mots-cles : "votre proth",
  "chez moi", convivial, ecoute, "ma" methode, accueil chaleureux.
  Adapte pour : commerce de proximite, salon de quartier, prothesiste de quartier.
"""


def _client_anthropic():
    if anthropic is None:
        raise RuntimeError("anthropic non installe. pip install anthropic")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY manquant dans .env")
    return anthropic.Anthropic()


def _famille_pour(metier: str) -> str:
    metier_low = metier.lower()
    for cle, famille in FAMILLE_PAR_METIER.items():
        if cle in metier_low:
            return famille
    return "wellness"


def _format_photos(photo_selection: dict) -> str:
    """Formatte la selection de photos en texte pour le prompt."""
    photos_dict = {p["fichier"]: p for p in photo_selection.get("photos", [])}
    lignes = []
    for fichier in photo_selection.get("ordre_galerie", []):
        info = photos_dict.get(fichier, {})
        lignes.append(f"  - {fichier} [{info.get('categorie','?')}] : {info.get('description','')}")
    return "\n".join(lignes) or "(pas de photos)"


def _prompt_systeme(metier: str, ville: str) -> str:
    famille = _famille_pour(metier)
    return f"""Tu es un directeur de creation specialise dans les sites web de
commercants locaux (petites entreprises, indépendants) en France. Tu connais les
codes de chaque sous-metier et tu produis des sites qui suivent les codes du
SOUS-METIER PRECIS de la marque, avec une personnalite issue de la marque elle-meme.

CONTEXTE GLOBAL : metier annonce = "{metier}" a {ville} (famille : {famille})

ETAPE 1 - IDENTIFIE LE SOUS-METIER PRECIS
Le metier annonce est trop large. En lisant la bio + les categories de photos,
tu dois identifier le sous-metier reel parmi cette liste de reference :

{SOUS_METIERS_REFERENCE}

ETAPE 2 - DETECTE LE PROFIL SONCAS
Identifie les 1 ou 2 leviers SONCAS dominants de la clientele cible (basee
sur le sous-metier identifie + ce que dit la marque dans sa bio) :

{SONCAS_REFERENCE}

ETAPE 3 - PRODUIS LE BRIEF + LA COPY

REGLES PALETTE (CRITIQUE) :
- La palette DOIT correspondre au sous-metier identifie a l'etape 1.
  Ex : si tu identifies "epilation laser", palette OBLIGATOIREMENT bleu clinique +
  blanc + vert eau. JAMAIS bordeaux/rouge meme si la bio mentionne onglerie en
  side activity.
- A l'interieur des codes du sous-metier, personnalise avec les couleurs
  observees sur les photos (ex : si onglerie + bcp de rouge sur les photos,
  accent rouge ; si epilation laser + photos avec touches turquoise, accent
  turquoise).
- 4 couleurs hex : primaire (accent fort), secondaire (accent doux),
  neutre_fonce (texte), neutre_clair (fond).

REGLES POUR LE TON DE LA COPY :
- Detecte si la bio est formelle (vous) ou casual (tu, tutoiement) et garde ce ton.
- Adapte le vocabulaire au levier SONCAS dominant (ex : Securite => "materiel
  certifie", "protocole maitrise" ; Sympathie => "ma cabine", "vous accueillir
  chez moi").
- Mentionne la ville {ville} naturellement (1 a 2 fois max sur l'ensemble).
- Reste FACTUEL : ne pas inventer des services, chiffres, certifications qui
  ne sont pas dans la bio/photos.
- ATTENTION ORTHOGRAPHE : francais impeccable. Verifie les accents (e/e/e),
  les accords sujet-verbe, les apostrophes typographiques ('). Pas de fautes.

REGLES POUR LE NOM COMMERCIAL (CRITIQUE) :
- Ce nom est affiche partout (logo header, footer, SEO title). Il DOIT etre
  un vrai nom de marque court, pas un titre de profil descriptif.
- Logique d'extraction depuis le fullName Insta :
  1. Si le fullName contient un VRAI prenom (Marianne, Nelly, Claire...) avec
     ou sans separateur, utilise juste le prenom (ou prenom + nom court de
     salon s'il y en a un). Ex : "Marianne | Esthéticienne | Spécialiste peau"
     -> nom_commercial = "Marianne".
  2. Si le fullName est un nom de salon clair (Beauty Bar Caudéran,
     Institut Beauty Pure, ART-INNEL, La Maison de Sophie), utilise-le tel
     quel (debarrasse des "•","|","🇫🇷" etc).
  3. Si le fullName est juste une description metier ("Esthéticienne
     Bordeaux diplômée, certifié", "Prothésiste ongulaire", "Coach mental")
     SANS nom propre, alors invente un nom propre court a partir du handle
     Instagram, en le rendant elegant :
       @beaute_oks -> "Beauté OKS"
       @marianne_miseenbeaute -> "Marianne Mise en Beauté"
       @institut_zen_33 -> "Institut Zen"
     Garde 1-3 mots max, capitalisation propre.
  4. Le nom_commercial NE DOIT JAMAIS contenir :
     - Des mots metier generiques (Esthéticienne, Prothésiste, Coach) SAUF
       s'ils font partie d'un vrai nom de salon ("Institut Beauty Pure" OK).
     - Des virgules ou enumerations ("Diplomee, certifie" = INTERDIT).
     - Des emojis, separateurs |, •, /, -.
     - Plus de 4 mots.
- Le H1 (titre principal hero) NE DOIT JAMAIS etre un titre metier generique.
  INTERDIT : "Estheticienne Bordeaux", "Prothesiste Ongulaire", "Coach
  Sportif", "Sophrologue Diplomee". Le H1 doit etre une promesse client
  emotionnelle teintee SONCAS.

REGLES POUR LES PHOTOS DE SERVICES (NOUVEAU) :
- Chaque service DOIT etre associe a la photo de la galerie la plus
  pertinente visuellement. Tu vois les descriptions de chaque photo dans
  l'ordre_galerie.
- Pour CHAQUE service tu fournis dans le champ "photo_index" : l'index 0-based
  de la photo dans ordre_galerie (0 = 1ere photo, 1 = 2eme, etc.).
- Une photo peut servir plusieurs services (si elle correspond), mais
  privilegie la diversite si possible.
- Si aucune photo ne colle, mets photo_index: 0 (par defaut).
- Exemples : service "Manucure" -> photo decrite comme "manucure rouge gros plan",
  service "Extensions cils" -> photo "extensions cils close-up", service
  "Epilation laser" -> photo "seance laser cabine", etc.

FORMAT DE REPONSE : JSON STRICT, rien autour, rien dans des balises ``` :
{{
  "sous_metier_detecte": "onglerie | lash | epilation_laser | soins_peau | massage | maquillage | sophrologue | naturopathe | coach_sportif | autre",
  "soncas_dominants": ["levier1", "levier2"],
  "brand_voice": {{
    "ton": "formel | casual | mixte",
    "style": "luxe | accessible | jeune | expert | decontracte",
    "mots_cles_identite": ["mot1", "mot2", "mot3"],
    "argument_unique": "Ce qui rend cette marque speciale en 1 phrase, deja teinte SONCAS"
  }},
  "palette": {{
    "primaire": "#RRGGBB",
    "secondaire": "#RRGGBB",
    "neutre_fonce": "#RRGGBB",
    "neutre_clair": "#RRGGBB",
    "raison": "Pourquoi ces couleurs collent au sous-metier identifie ET a cette marque"
  }},
  "typographie": {{
    "titre_font": "Nom de la Google Font (ex: Playfair Display)",
    "texte_font": "Nom de la Google Font (ex: Inter)"
  }},
  "nom_commercial": "Reprend exactement le fullName Insta, sans emoji ni reformulation",
  "copy": {{
    "h1": "Titre principal hero, integre SONCAS dominant (max 60 char). Ne dis JAMAIS 'Prothesiste Ongulaire' ou 'Estheticienne' comme titre, c'est ringard.",
    "tagline": "Sous-titre hero (1 phrase, max 100 char) qui prolonge SONCAS",
    "about_titre": "Titre de la section a propos (ex: 'Bienvenue chez X', 'Mon approche', etc.)",
    "about_texte": "3-4 phrases (200-400 char) qui presentent la marque, dans le ton + SONCAS",
    "services_titre": "Titre de la section services",
    "services": [
      {{"nom": "Nom court du service", "description": "1 phrase descriptive teintee SONCAS", "prix": "ex: A partir de 35 EUR ou ''", "duree": "ex: 1h ou ''", "photo_index": 0}}
    ],
    "raisons_titre": "Titre de la section pourquoi me choisir (ex: 'Pourquoi choisir le Beauty Bar ?')",
    "raisons": [
      {{"titre": "Raison courte (3-5 mots)", "texte": "1 phrase qui developpe, ancre dans SONCAS"}}
    ],
    "galerie_titre": "Titre de la section galerie (ex: 'Resultats clients', 'Mes realisations')",
    "cta_principal": "Texte du bouton principal (ex: 'Reserver mon soin', 'Prendre rendez-vous')",
    "cta_secondaire": "Texte du bouton secondaire (ex: 'Voir les prestations')",
    "footer_tagline": "Phrase courte de pied de page"
  }},
  "meta": {{
    "title": "Title SEO (50-60 char, contient nom commercial + ville + sous-metier)",
    "description": "Meta description SEO (150-160 char), teintee SONCAS"
  }}
}}

NOMBRE DE SERVICES : 4 a 6 (deductibles de la bio + descriptions photos).
NOMBRE DE RAISONS : 3, distinctes et concretes (pas vagues, pas redondantes).
INTERDICTIONS :
- NE JAMAIS inventer de chiffres (annees d'experience, nb clients, %).
- NE JAMAIS mettre des noms genericos comme titre principal ou h1.
- NE JAMAIS donner une palette bordeaux/rouge a une marque medico-esthetique
  (epilation laser, anti-age technique).
- NE JAMAIS mettre des fautes d'orthographe. Relis avant de repondre.
"""


def genere_brand_et_copy(dossier_site: Path, metier: str, ville: str) -> dict | None:
    """Lit metadata.json + photo_selection.json, produit brand_and_copy.json."""
    meta_path = dossier_site / "metadata.json"
    sel_path = dossier_site / "photo_selection.json"
    if not meta_path.exists() or not sel_path.exists():
        print(f"  [brand-error] Il manque metadata.json ou photo_selection.json dans {dossier_site}")
        return None

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    selection = json.loads(sel_path.read_text(encoding="utf-8"))

    desc_photos = _format_photos(selection)
    contexte_marque = f"""DONNEES BRUTES DE LA MARQUE :

Nom commercial : {metadata.get('fullName', '')}
Handle Instagram : @{metadata.get('handle', '')}
Categorie Insta : {metadata.get('businessCategoryName', '')}
Followers : {metadata.get('followersCount', 0)}
Bio :
\"\"\"
{metadata.get('biography', '')}
\"\"\"
Lien externe : {metadata.get('externalUrl', 'aucun')}

PHOTOS SELECTIONNEES POUR LA GALERIE (du meilleur au moins bon) :
{desc_photos}

SYNTHESE DU CURATEUR PHOTO :
{selection.get('synthese', '')}
"""

    print(f"  [brand+copy] Generation pour @{metadata.get('handle','?')} via {MODELE_COPY}...")
    client = _client_anthropic()
    resp = client.messages.create(
        model=MODELE_COPY,
        max_tokens=4096,
        system=_prompt_systeme(metier, ville),
        messages=[{"role": "user", "content": contexte_marque}],
    )

    texte = resp.content[0].text.strip()
    if "```" in texte:
        texte = texte.split("```json", 1)[-1].split("```", 1)[0].strip() if "```json" in texte \
            else texte.split("```", 1)[-1].split("```", 1)[0].strip()

    try:
        brief = json.loads(texte)
    except json.JSONDecodeError as e:
        print(f"  [brand-error] JSON parse fail : {e}")
        print(f"  Reponse brute : {texte[:800]}")
        return None

    cout = (resp.usage.input_tokens / 1_000_000 * 3.0) + (resp.usage.output_tokens / 1_000_000 * 15.0)
    brief["_meta"] = {
        "modele": resp.model,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "cout_estime_usd": round(cout, 4),
        "metier": metier,
        "ville": ville,
    }

    chemin_out = dossier_site / "brand_and_copy.json"
    chemin_out.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [brand+copy] sauve dans {chemin_out.name}")
    print(f"  [brand+copy] cout : ~${cout:.3f} ({resp.usage.input_tokens} in + {resp.usage.output_tokens} out)")
    return brief


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: python brand_and_copy.py <dossier_site> <metier> <ville>")
        print("ex:    python brand_and_copy.py output/sites/institut-beauty-bar 'esthéticienne' 'Bordeaux'")
        return 1

    dossier = Path(sys.argv[1])
    metier = sys.argv[2]
    ville = sys.argv[3]
    brief = genere_brand_et_copy(dossier, metier, ville)
    if not brief:
        return 1

    print(f"\nSous-metier : {brief.get('sous_metier_detecte','?')}")
    print(f"SONCAS      : {' + '.join(brief.get('soncas_dominants', []))}")
    print(f"Brand voice : {brief['brand_voice']['ton']} / {brief['brand_voice']['style']}")
    print(f"  Argument unique : {brief['brand_voice']['argument_unique']}")
    print(f"Palette     : {brief['palette']['primaire']} / {brief['palette']['secondaire']} / {brief['palette']['neutre_fonce']}")
    print(f"  Raison    : {brief['palette'].get('raison','')}")
    print(f"Nom comm    : {brief.get('nom_commercial','?')}")
    print(f"Typo        : {brief['typographie']['titre_font']} + {brief['typographie']['texte_font']}")
    print()
    print(f"H1          : {brief['copy']['h1']}")
    print(f"Tagline     : {brief['copy']['tagline']}")
    print(f"About       : {brief['copy']['about_texte'][:200]}")
    print(f"Services    : {len(brief['copy']['services'])} services")
    for s in brief['copy']['services']:
        print(f"  - {s['nom']:<35} {s.get('prix',''):<20} | {s['description'][:60]}")
    print(f"CTA princ   : {brief['copy']['cta_principal']}")
    print(f"SEO title   : {brief['meta']['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
