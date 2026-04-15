"""
MappingAgent
- Takes extracted field values and the original template structure
- Uses the LLM to compose the final filled specification document
- Follows the original template layout and sections
- Returns the final spec as Markdown
"""
import json
from typing import Optional
from app.agents.llm_client import get_llm_client, BaseLLMClient


MAPPING_SYSTEM_PROMPT = """Tu es un expert en rédaction de spécifications techniques et fonctionnelles.
Tu composes des documents de spécification complets, professionnels et bien structurés en Markdown.
Tu suis fidèlement la structure du template original."""


COMPOSE_PROMPT = """Tu dois composer un document de spécification complet en remplissant le template ci-dessous
avec les valeurs extraites automatiquement d'un repository de code.

## Structure du template original:
{template_text}

## Valeurs extraites pour chaque champ:
{extracted_values}

## Champs détectés avec contexte:
{fields_json}

## Instructions:
- Reproduis fidèlement la structure du template (titres, sous-titres, tableaux).
- Remplace les sections "à renseigner", les crochets [...], et les champs vides par les valeurs extraites.
- Si une valeur est "Non identifié", indique "[Non identifié - à compléter manuellement]".
- Garde le formatage professionnel en Markdown.
- Les tableaux doivent être en Markdown.
- Écris en français.
- N'invente PAS d'informations qui ne sont pas dans les valeurs extraites.

Génère le document de spécification complet:
"""


class MappingAgent:
    """Composes the final filled specification following the template structure."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()

    def compose(
        self,
        template_text: str,
        extracted_values: dict[str, str],
        fields: list[dict],
    ) -> str:
        """
        Compose the final spec document by filling the template with extracted values.
        Returns: Markdown string of the filled specification.
        """
        prompt = COMPOSE_PROMPT.format(
            template_text=template_text[:8000],
            extracted_values=json.dumps(extracted_values, ensure_ascii=False, indent=2),
            fields_json=json.dumps(fields, ensure_ascii=False, indent=2),
        )
        return self.llm.generate(prompt, system_prompt=MAPPING_SYSTEM_PROMPT)
