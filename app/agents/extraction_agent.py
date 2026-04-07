"""
ExtractionAgent
- Takes repo metadata and a list of LLM-detected fields from any template
- Uses the LLM to extract/infer the best value for each field
- Returns a dict {field_id: extracted_value}
"""
import json
from typing import Optional
from app.agents.llm_client import get_llm_client, BaseLLMClient


EXTRACTION_SYSTEM_PROMPT = """Tu es un expert en analyse de code et data engineering.
Tu analyses des métadonnées de repositories (README, structure, fichiers SQL/Python, etc.)
et tu extrais des informations précises pour remplir les champs d'une spécification.
Réponds toujours en JSON valide uniquement, sans texte supplémentaire."""


EXTRACTION_PROMPT = """Tu dois extraire des informations à partir des métadonnées d'un repository pour remplir les champs suivants d'une spécification technique.

## Métadonnées du repository:
{metadata_summary}

## Champs à remplir:
{fields_description}

## Instructions:
- Pour chaque champ, fournis une valeur pertinente, concise et précise basée sur les métadonnées du repository.
- Adapte la longueur de la réponse au type du champ (text=court, paragraph=détaillé, list=liste à puces, choice=un choix, table=tableau markdown).
- Si l'information n'est pas disponible dans les métadonnées, indique "Non identifié".
- Réponds UNIQUEMENT avec un objet JSON valide où les clés sont les "id" des champs.

Format de réponse:
{{
  "field_id": "valeur extraite",
  ...
}}
"""


class ExtractionAgent:
    """Uses an LLM to extract values for each detected template field from repo metadata."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()

    def extract(self, repo_metadata: dict, fields: list[dict]) -> dict[str, str]:
        """
        Extract values for all detected fields from repo metadata.
        fields: list of {id, label, section, description, type, required, options}
        Returns a dict {field_id: value}.
        """
        metadata_summary = self._prepare_metadata_summary(repo_metadata)
        fields_description = self._format_fields(fields)
        field_ids = [f["id"] for f in fields]

        prompt = EXTRACTION_PROMPT.format(
            metadata_summary=metadata_summary,
            fields_description=fields_description,
        )

        raw = self.llm.generate(prompt, system_prompt=EXTRACTION_SYSTEM_PROMPT)
        return self._parse_json_response(raw, field_ids)

    def _format_fields(self, fields: list[dict]) -> str:
        lines = []
        for f in fields:
            parts = [f'- id="{f["id"]}" | label="{f.get("label", "")}"']
            if f.get("section"):
                parts.append(f'section="{f["section"]}"')
            if f.get("description"):
                parts.append(f'description="{f["description"]}"')
            if f.get("type"):
                parts.append(f'type={f["type"]}')
            if f.get("options"):
                parts.append(f'options={f["options"]}')
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def _prepare_metadata_summary(self, metadata: dict) -> str:
        parts = []
        parts.append(f"Nom du repo: {metadata.get('repo_name', 'N/A')}")
        parts.append(f"Owner: {metadata.get('owner', 'N/A')}")
        parts.append(f"Description: {metadata.get('description', 'N/A')}")
        parts.append(f"Langages: {metadata.get('languages', 'N/A')}")
        parts.append(f"Topics: {metadata.get('topics', 'N/A')}")

        if metadata.get("readme"):
            parts.append(f"\n## README (extrait):\n{metadata['readme'][:3000]}")

        if metadata.get("structure"):
            files = metadata["structure"].get("files", [])
            file_list = [f["path"] for f in files[:40]]
            parts.append(f"\n## Structure des fichiers:\n{json.dumps(file_list, ensure_ascii=False)}")

        if metadata.get("sql_files"):
            parts.append(f"\n## Fichiers SQL ({len(metadata['sql_files'])}):")
            for sql in metadata["sql_files"][:5]:
                content = sql.get("content", "")[:1500]
                parts.append(f"### {sql['path']}:\n```sql\n{content}\n```")

        if metadata.get("python_files"):
            parts.append(f"\n## Fichiers Python ({len(metadata['python_files'])}):")
            for py in metadata["python_files"][:5]:
                content = py.get("content", "")[:1500]
                parts.append(f"### {py['path']}:\n```python\n{content}\n```")

        return "\n".join(parts)

    def _parse_json_response(self, raw: str, field_ids: list[str]) -> dict[str, str]:
        """Try to parse LLM JSON response, fallback gracefully."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        raw = raw.strip()

        try:
            data = json.loads(raw)
            return {fid: str(data.get(fid, "Non identifié")) for fid in field_ids}
        except json.JSONDecodeError:
            return {fid: "Non identifié" for fid in field_ids}
