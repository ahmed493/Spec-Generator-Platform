"""
TemplateAgent — Universal Template Parser
- Reads any template (PDF or Markdown) without requiring {{placeholders}}
- Uses LLM to analyze the template structure and detect all fields/sections to fill
- Returns a structured list of detected fields with their context
"""
import json
from typing import Optional
from app.agents.llm_client import get_llm_client, BaseLLMClient
from app.agents.prompts.template_prompts import (
    DETECT_FIELDS_SYSTEM_PROMPT,
    DETECT_FIELDS_PROMPT,
)

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
        Use LLM to analyze the template and detect ALL fields/sections to fill.
        Splits long templates into overlapping chunks so no field is ever missed.
        Returns: {template_title, sections, fields: [{id, label, section, description, type, required, options}]}
        """
        CHUNK_SIZE = 10000   # chars per chunk (fits well within gpt-4o-mini context)
        OVERLAP    = 800     # overlap between chunks so fields near boundaries aren't missed

        # Split template into overlapping chunks
        chunks = []
        start = 0
        while start < len(template_text):
            end = start + CHUNK_SIZE
            chunks.append(template_text[start:end])
            if end >= len(template_text):
                break
            start = end - OVERLAP  # back up by overlap so we don't cut mid-section

        total = len(chunks)
        all_sections: list[str] = []
        all_fields: list[dict] = []
        template_title = "Unknown Template"
        seen_ids: set[str] = set()

        for idx, chunk in enumerate(chunks):
            prompt = DETECT_FIELDS_PROMPT.format(
                template_text=chunk,
                chunk_index=idx + 1,
                chunk_total=total,
            )
            raw = self.llm.generate(prompt, system_prompt=DETECT_FIELDS_SYSTEM_PROMPT)
            parsed = self._parse_json_response(raw)

            # Take the title from the first chunk only
            if idx == 0 and parsed.get("template_title"):
                template_title = parsed["template_title"]

            # Merge sections (deduplicated)
            for sec in parsed.get("sections", []):
                if sec and sec not in all_sections:
                    all_sections.append(sec)

            # Merge fields — deduplicate by id, then by (label+section) similarity
            for field in parsed.get("fields", []):
                fid = field.get("id", "").strip()
                if not fid:
                    continue

                # If id already seen, try label+section dedup
                if fid in seen_ids:
                    label = field.get("label", "").lower().strip()
                    section = field.get("section", "").lower().strip()
                    duplicate = any(
                        f.get("label", "").lower().strip() == label
                        and f.get("section", "").lower().strip() == section
                        for f in all_fields
                    )
                    if duplicate:
                        continue
                    # Different field that happens to have the same id — make id unique
                    fid = f"{fid}_{idx}"
                    field["id"] = fid

                seen_ids.add(fid)
                all_fields.append(field)

        return {
            "template_title": template_title,
            "sections": all_sections,
            "fields": all_fields,
        }

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
