# ── System prompt ─────────────────────────────────────────────────────────────

DETECT_FIELDS_SYSTEM_PROMPT = """Tu es un expert en analyse de documents et spécifications techniques.
Tu analyses des templates de spécification et tu identifies TOUS les champs, sections et tableaux
qui doivent être remplis avec des informations spécifiques à un projet.
Réponds UNIQUEMENT en JSON valide. N'omets AUCUN champ, même s'il semble mineur."""


# ── User prompt ───────────────────────────────────────────────────────────────

DETECT_FIELDS_PROMPT = """Analyse le template de spécification suivant et identifie TOUS les champs/sections qui doivent être remplis.

## Contenu du template (partie {chunk_index}/{chunk_total}):
{template_text}

## Instructions:
Identifie CHAQUE champ ou section qui attend une valeur à renseigner. Cela inclut:
- Les champs marqués "à renseigner", "[...]", "XX", "N/A à compléter"
- Les sections entre crochets [...] qui contiennent des instructions
- Les cellules de tableau vides ou avec des pointillés
- Les choix à faire (OUI/NON, type de fichier, etc.)
- Les sections descriptives qui doivent être rédigées
- Les lignes de tableau avec libellé mais colonne valeur vide
- TOUS les champs même si le template est long — n'en saute aucun

Pour chaque champ détecté, fournis:
- "id": un identifiant unique court en snake_case (préfixe avec la section pour éviter les doublons)
- "label": le nom lisible du champ
- "section": la section du template où il se trouve
- "description": ce qui est attendu (basé sur le contexte du template)
- "type": "text" | "choice" | "table" | "paragraph" | "list"
- "required": true/false
- "options": liste d'options si type="choice", sinon null

Réponds UNIQUEMENT avec un JSON valide:
{{
  "template_title": "Titre du template",
  "sections": ["liste des sections principales de cette partie"],
  "fields": [
    {{
      "id": "...",
      "label": "...",
      "section": "...",
      "description": "...",
      "type": "...",
      "required": true,
      "options": null
    }}
  ]
}}
"""
