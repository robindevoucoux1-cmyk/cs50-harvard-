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


CODES_SECTEUR = {
    "esthéticienne": {
        "famille_template": "beaute",
        "palette_inspirations": "Tons feminins, neutres chauds (rose poudre, beige, taupe, bordeaux, or rose, blanc casse, marron chocolat). Eviter neon et couleurs froides. La couleur d'accent doit etre inspiree des photos (ex : rouge si manucure rouge dominante, vert sauge si soins naturels).",
        "typographie": "Serif elegante pour les titres (Playfair Display, Cormorant), Sans serif moderne pour le texte (Inter, Outfit).",
        "mood": "Luxe accessible, feminin, soin de soi, douceur, prise en main pro.",
        "sections": ["Hero", "A propos / Mon approche", "Services & prestations", "Galerie resultats", "Pourquoi me choisir", "Reserver"],
        "exemples_cta": ["Reserver mon soin", "Prendre rendez-vous", "Decouvrir mes prestations", "Mes prestations"],
        "exemples_h1": ["Sublimez votre peau a Bordeaux", "L'art de la beaute, au naturel", "Votre rituel beaute sur mesure"],
    },
    "coach sportif": {
        "famille_template": "sport",
        "palette_inspirations": "Couleurs energiques : noir profond + orange vif, noir + jaune lime, bleu electrique + blanc, vert neon. Contraste fort, look athletique.",
        "typographie": "Sans serif puissant (Inter Black, Anton, Bebas Neue) pour les titres, Inter Regular pour le texte.",
        "mood": "Energie, transformation, depassement, mental d'acier, communaute.",
        "sections": ["Hero", "Mon approche", "Programmes (Fit / Muscu / Cardio)", "Resultats clients", "Pourquoi moi", "Reserver une seance d'essai"],
        "exemples_cta": ["Demarrer ma transformation", "Reserver ma seance d'essai", "Booker mon coach"],
        "exemples_h1": ["Transformez-vous, durablement", "Le coach qui change la donne a Bordeaux"],
    },
    "sophrologue": {
        "famille_template": "wellness",
        "palette_inspirations": "Tons apaisants : vert sauge, bleu lavande, beige sable, lin, ocre doux. Naturalite, calme. Aucune couleur vive.",
        "typographie": "Serif douce (Cormorant, Lora) pour les titres, Sans serif minimaliste pour le texte.",
        "mood": "Calme, ressourcement, lacher prise, ecoute, pratique de l'instant.",
        "sections": ["Hero", "La sophrologie & moi", "Seances proposees", "Pour qui", "Temoignages", "Reserver"],
        "exemples_cta": ["Reserver ma seance", "Prendre rendez-vous", "Faire le premier pas"],
        "exemples_h1": ["Retrouver son equilibre, ici et maintenant", "La sophrologie, douce et accessible"],
    },
    "naturopathe": {
        "famille_template": "wellness",
        "palette_inspirations": "Vert sauge, vert olive, terracotta, beige naturel, blanc creme. Nature, simplicite.",
        "typographie": "Serif (Cormorant, Lora) + Sans serif minimaliste.",
        "mood": "Hygiene de vie, plantes, accompagnement holistique, scientifique mais doux.",
        "sections": ["Hero", "Approche & formation", "Consultations", "Domaines d'expertise", "Temoignages", "Reserver"],
        "exemples_cta": ["Prendre rendez-vous", "Reserver ma consultation"],
        "exemples_h1": ["Votre sante au naturel, a Bordeaux"],
    },
}

CODES_PAR_DEFAUT = {
    "famille_template": "wellness",
    "palette_inspirations": "Tons sobres, beige et terracotta, ou navy et or, selon le metier.",
    "typographie": "Serif elegante pour les titres, Sans serif moderne pour le texte.",
    "mood": "Professionnalisme accessible, expertise visible.",
    "sections": ["Hero", "A propos", "Services", "Galerie", "Avis", "Contact"],
    "exemples_cta": ["Prendre rendez-vous", "Reserver", "Me contacter"],
    "exemples_h1": ["Au service de votre {metier} a {ville}"],
}


def _client_anthropic():
    if anthropic is None:
        raise RuntimeError("anthropic non installe. pip install anthropic")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY manquant dans .env")
    return anthropic.Anthropic()


def _codes_pour(metier: str) -> dict:
    metier_low = metier.lower()
    for cle, codes in CODES_SECTEUR.items():
        if cle in metier_low or metier_low in cle:
            return codes
    return CODES_PAR_DEFAUT


def _format_photos(photo_selection: dict) -> str:
    """Formatte la selection de photos en texte pour le prompt."""
    photos_dict = {p["fichier"]: p for p in photo_selection.get("photos", [])}
    lignes = []
    for fichier in photo_selection.get("ordre_galerie", []):
        info = photos_dict.get(fichier, {})
        lignes.append(f"  - {fichier} [{info.get('categorie','?')}] : {info.get('description','')}")
    return "\n".join(lignes) or "(pas de photos)"


def _prompt_systeme(metier: str, ville: str) -> str:
    codes = _codes_pour(metier)
    return f"""Tu es un directeur de creation specialise dans les sites web de
commercants locaux (petites entreprises, indépendants). Tu connais les codes de
chaque secteur et tu produis des sites qui ressemblent a leur marche, mais
avec une vraie personnalite issue de la marque elle-meme.

CONTEXTE METIER : {metier} a {ville}
- Famille de template a utiliser : {codes['famille_template']}
- Palette suggeree pour ce metier : {codes['palette_inspirations']}
- Typographie suggeree : {codes['typographie']}
- Mood/identite secteur : {codes['mood']}
- Sections types : {", ".join(codes['sections'])}
- Exemples de CTAs : {", ".join(codes['exemples_cta'])}

Ton travail : analyser la marque (bio + photos Instagram fournies via leurs
descriptions) et produire un brief de design complet + tous les textes du
site futur, dans le ton et l'identite specifique de cette marque.

REGLES POUR LA PALETTE :
- 3 couleurs hex : primaire (accent fort), secondaire (accent doux), neutre (texte/fond)
- Inspiree du metier MAIS personnalisee a partir des couleurs vues dans les
  photos (ex : si la marque fait des manucures rouges dominantes, le rouge devient
  l'accent primaire)
- Toujours coherente avec le mood du secteur (pas de neon chez une sophrologue)

REGLES POUR LE TON DE LA COPY :
- Detecte si la bio est formelle (vous) ou casual (tu, tutoiement) et garde ce ton
- Utilise les emojis presents dans la bio comme signal de style
- Mentionne la ville {ville} naturellement (pas force a chaque phrase)
- Reste FACTUEL : ne pas inventer des services qui ne sont pas dans la bio/photos
- Si la marque a un positionnement special detecte (luxe, accessible, jeune,
  experte, decontractee), adapte tout (h1, services, ctas) a ce positionnement

FORMAT DE REPONSE : JSON STRICT, RIEN D'AUTRE. Structure :
{{
  "brand_voice": {{
    "ton": "formel | casual | mixte",
    "style": "luxe | accessible | jeune | expert | decontracte",
    "mots_cles_identite": ["mot1", "mot2", "mot3"],
    "argument_unique": "Ce qui rend cette marque speciale en 1 phrase"
  }},
  "palette": {{
    "primaire": "#RRGGBB",
    "secondaire": "#RRGGBB",
    "neutre_fonce": "#RRGGBB",
    "neutre_clair": "#RRGGBB",
    "raison": "Pourquoi ces couleurs collent a cette marque specifique"
  }},
  "typographie": {{
    "titre_font": "Nom de la Google Font (ex: Playfair Display)",
    "texte_font": "Nom de la Google Font (ex: Inter)"
  }},
  "theme_template": "{codes['famille_template']}_<sous_variante>",
  "copy": {{
    "h1": "Titre principal hero (max 60 char)",
    "tagline": "Sous-titre hero (1 phrase, max 100 char)",
    "about_titre": "Titre de la section a propos",
    "about_texte": "3-4 phrases sur le commerce (200-400 char), dans le ton",
    "services_titre": "Titre de la section services",
    "services": [
      {{"nom": "Nom du service", "description": "1 phrase descriptive", "prix": "ex: A partir de 35 EUR ou ''"}}
    ],
    "raisons_titre": "Titre de la section pourquoi me choisir",
    "raisons": [
      {{"titre": "Raison courte", "texte": "1 phrase qui developpe"}}
    ],
    "galerie_titre": "Titre de la section galerie",
    "cta_principal": "Texte du bouton principal (ex: 'Reserver mon soin')",
    "cta_secondaire": "Texte du bouton secondaire (ex: 'Voir les prestations')",
    "footer_tagline": "Phrase courte de pied de page"
  }},
  "meta": {{
    "title": "Title SEO (50-60 char, contient ville et metier)",
    "description": "Meta description SEO (150-160 char)"
  }}
}}

Tu fournis 4 a 6 services (deductibles de la bio + descriptions photos).
Tu fournis 3 raisons distinctes et concretes (pas vagues).
Tu N'INVENTES PAS de chiffres (annees d'experience, nb clients) sauf si ils sont dans la bio.
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

    print(f"\nBrand voice : {brief['brand_voice']['ton']} / {brief['brand_voice']['style']}")
    print(f"  Argument unique : {brief['brand_voice']['argument_unique']}")
    print(f"Palette     : {brief['palette']['primaire']} / {brief['palette']['secondaire']} / {brief['palette']['neutre_fonce']}")
    print(f"Theme       : {brief['theme_template']}")
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
