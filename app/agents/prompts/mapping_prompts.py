# ── System prompts ────────────────────────────────────────────────────────────

SECTION_COMPOSE_SYSTEM = """Tu es un expert en rédaction de spécifications techniques data engineering.
Tu remplis une section d'un document de spécification avec des valeurs extraites automatiquement.
Tu suis fidèlement la structure et le format de la section du template.
Tu n'inventes pas d'information absente des valeurs fournies.
Réponds uniquement avec le contenu Markdown de la section remplie, sans commentaire supplémentaire."""

ASSEMBLY_SYSTEM = """Tu es un expert en rédaction de spécifications techniques.
Tu révises et harmonises un document de spécification complet pour s'assurer:
- Cohérence du ton et du style (professionnel, précis, en français)
- Cohérence des données entre les sections (mêmes noms de tables, technologies, etc.)
- Bonne numérotation des titres et sous-titres
- Tableaux Markdown bien formés
- Aucune section vide ou avec des placeholders non remplis
Retourne le document Markdown final complet, sans commentaire."""


# ── User prompts ──────────────────────────────────────────────────────────────

SECTION_COMPOSE_PROMPT = """Remplis cette section du document de spécification avec les valeurs extraites.

## Template de la section (à remplir):
{section_template}

## Valeurs extraites pour les champs de cette section:
{section_values}

## Instructions:
- Reproduis fidèlement la structure du template de la section (tableaux, listes, sous-titres).
- Remplace les placeholders ([...], "à renseigner", "XX", champs vides) par les valeurs fournies.
- Si une valeur est "Non identifié dans les sources analysées", écris "[À compléter]".
- Conserve les titres exacts du template.
- Pour les tableaux: garde toutes les colonnes, remplis toutes les lignes.
- Génère UNIQUEMENT le contenu Markdown de cette section (commence par le titre ##).
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
- Si une section a des "[À compléter]" évidents, essaie de les inférer depuis les autres sections.
- Retourne le document Markdown complet (de ## 1. à la dernière section).
"""
