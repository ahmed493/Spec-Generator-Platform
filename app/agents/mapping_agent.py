"""
MappingAgent — Section-by-Section Composition
Strategy:
  Pass 1 – Parse template into logical sections (by ## / ### headings)
  Pass 2 – Compose each section individually with its relevant field values
  Pass 3 – Assemble all sections + final coherence / prose-polish pass
"""
import json
import re
from typing import Optional
from app.agents.llm_client import get_llm_client, BaseLLMClient


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


class MappingAgent:
    """Section-by-section spec composition with final assembly pass."""

    MAX_SECTION_TEMPLATE_LEN = 3000  # chars of template text per section call
    MAX_ASSEMBLY_LEN = 18000         # chars for assembly prompt sections text

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def compose(
        self,
        template_text: str,
        extracted_values: dict[str, str],
        fields: list[dict],
        pipeline_context: str = "",
    ) -> str:
        """
        Three-pass composition:
          1. Parse template into sections
          2. Compose each section independently
          3. Assemble + coherence pass
        """
        # Build section→fields mapping
        fields_by_section = self._group_fields_by_section(fields, extracted_values)

        # Parse template into sections
        sections = self._parse_template_sections(template_text)

        if not sections:
            # Fallback: single-call compose if template has no headings
            return self._fallback_compose(template_text, extracted_values, fields)

        # Pass 2: compose each section individually
        composed_sections: list[str] = []
        for sec_title, sec_body in sections:
            matching_values = self._match_values_to_section(
                sec_title, sec_body, fields_by_section
            )
            composed = self._compose_section(sec_title, sec_body, matching_values)
            composed_sections.append(composed)

        # Pass 3: assembly + coherence pass
        assembled = self._assemble(composed_sections, pipeline_context)
        return assembled

    # ─────────────────────────────────────────────────────────────────────────
    # Section parsing
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_template_sections(self, template_text: str) -> list[tuple[str, str]]:
        """
        Split the template at top-level ## headings.
        Returns list of (heading_line, body_text) tuples.
        """
        # Match ## or # level headings (not ###)
        pattern = re.compile(r"^(#{1,2} .+)$", re.MULTILINE)
        matches = list(pattern.finditer(template_text))

        if not matches:
            return []

        sections = []
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(template_text)
            body = template_text[start:end].strip()
            sections.append((title, body))
        return sections

    # ─────────────────────────────────────────────────────────────────────────
    # Section composition
    # ─────────────────────────────────────────────────────────────────────────

    def _group_fields_by_section(
        self, fields: list[dict], extracted_values: dict[str, str]
    ) -> dict[str, dict[str, str]]:
        """Map section_name → {field_id: value}."""
        grouped: dict[str, dict[str, str]] = {}
        for f in fields:
            sec = f.get("section", "Général") or "Général"
            fid = f["id"]
            val = extracted_values.get(fid, "Non identifié dans les sources analysées")
            grouped.setdefault(sec, {})[fid] = val
        return grouped

    def _match_values_to_section(
        self,
        sec_title: str,
        sec_body: str,
        fields_by_section: dict[str, dict[str, str]],
    ) -> dict[str, str]:
        """
        Find the section group(s) whose name overlaps best with the template section title.
        Falls back to fuzzy keyword matching.
        """
        title_lower = sec_title.lower()
        best_match: dict[str, str] = {}

        for section_name, values in fields_by_section.items():
            sec_lower = section_name.lower()
            # Direct containment match
            if sec_lower in title_lower or title_lower in sec_lower:
                best_match.update(values)
                continue
            # Keyword overlap
            title_words = set(re.findall(r"\w{4,}", title_lower))
            sec_words   = set(re.findall(r"\w{4,}", sec_lower))
            if title_words & sec_words:
                best_match.update(values)

        # If nothing matched, include all values as fallback context
        if not best_match:
            for values in fields_by_section.values():
                best_match.update(values)

        return best_match

    def _compose_section(self, title: str, body: str, values: dict[str, str]) -> str:
        """Compose a single template section with its extracted values."""
        # Build a clean values block (label if available, else id)
        values_text = json.dumps(values, ensure_ascii=False, indent=2)

        section_template = f"{title}\n\n{body}"[:self.MAX_SECTION_TEMPLATE_LEN]

        prompt = SECTION_COMPOSE_PROMPT.format(
            section_template=section_template,
            section_values=values_text[:4000],
        )
        result = self.llm.generate(prompt, system_prompt=SECTION_COMPOSE_SYSTEM)
        # Ensure it starts with the heading
        result = result.strip()
        if not result.startswith("#"):
            result = f"{title}\n\n{result}"
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Assembly
    # ─────────────────────────────────────────────────────────────────────────

    def _assemble(self, composed_sections: list[str], pipeline_context: str) -> str:
        """Final assembly + coherence pass."""
        joined = "\n\n---\n\n".join(composed_sections)

        # If very short doc, return as-is (avoid unnecessary call)
        if len(joined) < 400:
            return joined

        # Truncate for the prompt if very long
        truncated = joined[:self.MAX_ASSEMBLY_LEN]
        if len(joined) > self.MAX_ASSEMBLY_LEN:
            truncated += f"\n\n... [{len(joined) - self.MAX_ASSEMBLY_LEN} chars supplémentaires tronqués pour le prompt d'assemblage]"

        prompt = ASSEMBLY_PROMPT.format(
            sections_text=truncated,
            pipeline_context=pipeline_context[:1500] if pipeline_context else "Non spécifié.",
        )
        assembled = self.llm.generate(prompt, system_prompt=ASSEMBLY_SYSTEM)
        return assembled.strip()

    # ─────────────────────────────────────────────────────────────────────────
    # Fallback (no headings in template)
    # ─────────────────────────────────────────────────────────────────────────

    def _fallback_compose(
        self,
        template_text: str,
        extracted_values: dict[str, str],
        fields: list[dict],
    ) -> str:
        """Original single-call compose, used when template has no ## headings."""
        prompt = (
            "Remplis ce template de spécification avec les valeurs extraites.\n\n"
            f"## Template:\n{template_text[:6000]}\n\n"
            f"## Valeurs extraites:\n{json.dumps(extracted_values, ensure_ascii=False, indent=2)[:6000]}\n\n"
            "Instructions: Remplace tous les placeholders par les valeurs fournies. "
            "Génère le document Markdown complet."
        )
        return self.llm.generate(prompt, system_prompt=SECTION_COMPOSE_SYSTEM)
