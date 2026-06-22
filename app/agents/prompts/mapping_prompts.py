# ── System prompts ────────────────────────────────────────────────────────────

SECTION_COMPOSE_SYSTEM = """Tu es un expert en rédaction de spécifications techniques data engineering.
Tu remplis une section d'un document de spécification avec des valeurs extraites automatiquement.
Tu suis STRICTEMENT la structure et le format du template — tu ne reformules pas, tu ne développes pas.
RÈGLE ABSOLUE: tu n'inventes JAMAIS d'information. Si une valeur est manquante, absente ou NOT_FOUND,
tu écris UNIQUEMENT "[À compléter]" à la place du placeholder. Tu n'expliques pas, tu ne génères pas
de contenu inventé, tu ne décris pas le champ manquant.
Réponds uniquement avec le contenu Markdown de la section remplie, sans commentaire supplémentaire."""

ASSEMBLY_SYSTEM = """Tu es un expert en rédaction de spécifications techniques.
Tu révises et harmonises un document de spécification complet pour s'assurer:
- Cohérence du ton et du style (professionnel, précis, en français)
- Cohérence des données entre les sections (mêmes noms de tables, technologies, etc.)
- Bonne numérotation des titres et sous-titres
- Tableaux Markdown bien formés
RÈGLE ABSOLUE: ne remplis PAS les champs "[À compléter]" — laisse-les exactement tels quels.
Ne génère JAMAIS de contenu inventé pour les champs manquants.
Retourne le document Markdown final complet, sans commentaire."""


# ── User prompts ──────────────────────────────────────────────────────────────

SECTION_COMPOSE_PROMPT = """Remplis cette section du document de spécification avec les valeurs extraites.

## Template de la section (à remplir):
{section_template}

## Valeurs extraites disponibles (label: valeur):
{section_values}

## Instructions STRICTES:
- Les tableaux Markdown présents dans le template ont été pré-remplis automatiquement.
  REPRODUIS-LES EXACTEMENT tels quels — ne modifie PAS leur structure, ni leurs valeurs, ni le nombre de colonnes.
- Les valeurs sont listées sous forme "- Label: valeur". Utilise le label pour placer la valeur
  dans le bon champ textuel du template.
- Remplace chaque placeholder textuel ([...], "à renseigner", champ vide hors tableau) par la valeur correspondante.
- Si aucune valeur extraite ne correspond à un champ: écris UNIQUEMENT "[À compléter]".
  NE génère PAS de description, d'explication ou de contenu inventé.
- Conserve les titres et labels exacts du template, sans les modifier.
- Génère UNIQUEMENT le contenu Markdown de la section (commence directement par le titre ou le contenu).
"""

ASSEMBLY_PROMPT = """Voici les sections d'une spécification technique rédigées indépendamment.
Assemble-les en un document cohérent et harmonisé.

## Sections à assembler:
{sections_text}

## Informations de référence (pipeline ciblé):
{pipeline_context}

## Instructions:
- Assure la cohérence des données entre sections (ex: mêmes technologies, mêmes noms de tables).
- Corrige la numérotation des titres si nécessaire.
- Harmonise le style et le ton (professionnel, précis, en français).
- NE remplis PAS les champs "[À compléter]" — conserve-les exactement comme ils sont.
- NE génère PAS de contenu inventé pour compenser les données manquantes.
- Retourne le document Markdown complet.
"""
