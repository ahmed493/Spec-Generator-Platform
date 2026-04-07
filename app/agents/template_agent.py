"""
TemplateAgent — Universal Template Parser
- Reads any template (PDF or Markdown) without requiring {{placeholders}}
- Uses LLM to analyze the template structure and detect all fields/sections to fill
- Returns a structured list of detected fields with their context
"""
import json
from typing import Optional
from app.agents.llm_client import get_llm_client, BaseLLMClient


DETECT_FIELDS_SYSTEM_PROMPT = """Tu es un expert en analyse de documents et spécifications techniques.
Tu analyses des templates de spécification et tu identifies TOUS les champs, sections et tableaux
qui doivent être remplis avec des informations spécifiques à un projet.
Réponds UNIQUEMENT en JSON valide."""

DETECT_FIELDS_PROMPT = """Analyse le template de spécification suivant et identifie TOUS les champs/sections qui doivent être remplis.

## Contenu du template:
{template_text}

## Instructions:
Identifie chaque champ ou section qui attend une valeur à renseigner. Cela inclut:
- Les champs marqués "à renseigner"
- Les sections entre crochets [...] qui contiennent des instructions
- Les cellules de tableau vides à remplir
- Les choix à faire (OUI/NON, type de fichier, etc.)
- Les sections descriptives qui doivent être rédigées

Pour chaque champ détecté, fournis:
- "id": un identifiant unique court en snake_case
- "label": le nom lisible du champ
- "section": la section du template où il se trouve
- "description": ce qui est attendu (basé sur le contexte du template)
- "type": "text" | "choice" | "table" | "paragraph" | "list"
- "required": true/false
- "options": liste d'options si type="choice", sinon null

Réponds UNIQUEMENT avec un JSON:
{{
  "template_title": "Titre du template",
  "sections": ["liste des sections principales"],
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


class TemplateAgent:
    """Parses any template (PDF or Markdown) and uses LLM to detect fields to fill."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()

    def read_file(self, file_bytes: bytes, filename: str) -> str:
        """Read a template file (PDF or text) and return its text content."""
        lower = filename.lower()
        if lower.endswith(".pdf"):
            return self._read_pdf(file_bytes)
        else:
            return file_bytes.decode("utf-8", errors="replace")

    def detect_fields(self, template_text: str) -> dict:
        """
        Use LLM to analyze the template and detect all fields/sections to fill.
        Returns: {template_title, sections, fields: [{id, label, section, description, type, required, options}]}
        """
        truncated = template_text[:12000]
        prompt = DETECT_FIELDS_PROMPT.format(template_text=truncated)
        raw = self.llm.generate(prompt, system_prompt=DETECT_FIELDS_SYSTEM_PROMPT)
        return self._parse_json_response(raw)

    def _read_pdf(self, file_bytes: bytes) -> str:
        """Extract text from PDF bytes using pdfplumber."""
        import pdfplumber
        import io

        text_parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- Page {i+1} ---\n{page_text}")

                tables = page.extract_tables()
                for j, table in enumerate(tables):
                    table_lines = []
                    for row in table:
                        cleaned = [str(cell).strip() if cell else "" for cell in row]
                        if any(cleaned):
                            table_lines.append(" | ".join(cleaned))
                    if table_lines:
                        text_parts.append(f"\n[Tableau page {i+1}]\n" + "\n".join(table_lines))

        return "\n\n".join(text_parts)

    def _parse_json_response(self, raw: str) -> dict:
        """Parse LLM JSON response with fallback."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        raw = raw.strip()

        try:
            data = json.loads(raw)
            return {
                "template_title": data.get("template_title", "Unknown Template"),
                "sections": data.get("sections", []),
                "fields": data.get("fields", []),
            }
        except json.JSONDecodeError:
            return {
                "template_title": "Unknown Template",
                "sections": [],
                "fields": [],
                "error": "Failed to parse template fields from LLM response",
            }
