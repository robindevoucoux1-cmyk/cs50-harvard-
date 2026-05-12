# Vitriz Dashboard

Interface visuelle pour gerer les sites Vitriz.

## Installation (a faire une seule fois)

```bash
cd dashboard
pip install -r requirements.txt
cp .env.example .env
# Edite .env et colle ta cle ANTHROPIC_API_KEY (recuperee sur console.anthropic.com)
```

## Lancement

```bash
cd dashboard
python server.py
```

Ouvre ensuite **http://localhost:8000** dans Chrome / Safari.

## Ce que tu peux faire

- **Apercu** : voir le site live (mobile / tablet / desktop)
- **Edition** : modifier les champs (titre, tagline, FAQ, etc.) via formulaires
- **Theme** : changer la palette couleurs + polices en 1 clic
- **JSON** : editer le JSON brut si besoin
- **Chat IA** : decrire la modification en francais, l'IA propose un patch a appliquer

## Exemples de commandes IA

- *Change la couleur principale en bleu marine*
- *Reecris le hero pour etre plus chaleureux*
- *Ajoute une FAQ : Acceptez-vous les cartes bancaires ?*
- *Passe le titre en majuscules*
- *Change le theme en medical-mint*
