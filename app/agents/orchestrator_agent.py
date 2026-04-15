"""
OrchestratorAgent
Coordinates the full template-based spec generation workflow:
1. TemplateAgent    → read file (PDF/MD), detect fields via LLM
2. ExtractionAgent  → extract values from repo metadata for each field
3. MappingAgent     → compose the final filled spec following template structure
4. ValidationAgent  → validate all required fields are filled
"""
from typing import Optional
from app.agents.template_agent import TemplateAgent
from app.agents.extraction_agent import ExtractionAgent
from app.agents.mapping_agent import MappingAgent
from app.agents.validation_agent import ValidationAgent
from app.agents.llm_client import get_llm_client, BaseLLMClient


class OrchestratorAgent:
    """Orchestrates the multi-agent spec generation pipeline."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()
        self.template_agent = TemplateAgent(self.llm)
        self.extraction_agent = ExtractionAgent(self.llm)
        self.mapping_agent = MappingAgent(self.llm)
        self.validation_agent = ValidationAgent()

    def generate(self, file_bytes: bytes, filename: str, repo_metadata: dict) -> dict:
        """
        Full pipeline: read file → detect fields → extract → compose → validate.

        Returns:
        - spec: the final filled specification (Markdown)
        - template_text: raw text extracted from the uploaded file
        - fields: list of detected fields
        - extracted_values: raw extracted values per field
        - validation: validation report
        """

        # Step 1: Read uploaded file (PDF or text)
        template_text = self.template_agent.read_file(file_bytes, filename)

        if not template_text.strip():
            return {
                "spec": "",
                "template_text": "",
                "fields": [],
                "extracted_values": {},
                "validation": {
                    "is_valid": False,
                    "filled": [],
                    "missing": [],
                    "warnings": [],
                    "report": "Le fichier uploadé est vide ou illisible.",
                },
            }

        # Step 2: Detect fields from template using LLM
        detected = self.template_agent.detect_fields(template_text)
        fields = detected.get("fields", [])

        if not fields:
            return {
                "spec": template_text,
                "template_text": template_text,
                "fields": [],
                "extracted_values": {},
                "validation": {
                    "is_valid": False,
                    "filled": [],
                    "missing": [],
                    "warnings": [],
                    "report": "Aucun champ à remplir détecté dans le template.",
                },
            }

        # Step 3: Extract values from repo metadata for each detected field
        extracted_values = self.extraction_agent.extract(repo_metadata, fields)

        # Step 4: Validate extracted values
        validation = self.validation_agent.validate(fields, extracted_values)

        # Step 5: Compose the final filled spec using MappingAgent
        spec = self.mapping_agent.compose(template_text, extracted_values, fields)

        return {
            "spec": spec,
            "template_text": template_text,
            "template_title": detected.get("template_title", "Spécification"),
            "sections": detected.get("sections", []),
            "fields": fields,
            "extracted_values": extracted_values,
            "validation": validation,
        }
