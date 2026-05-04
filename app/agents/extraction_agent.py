"""
ExtractionAgent — Multi-Pass Chunked Extraction
Strategy:
  Pass 1  – Section-batched extraction (10 fields/call, context scoped to relevant files)
  Pass 2  – Deep-dive re-extraction for paragraph/table fields with thin answers
  Pass 3  – Synthesis / coherence: cross-field review to ensure consistency & richness
"""
import json
import re
from typing import Optional, TYPE_CHECKING
from app.agents.llm_client import get_llm_client, BaseLLMClient


# ── System prompts ────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """Tu es un expert en analyse de code et data engineering.
Tu analyses le contenu complet de repositories (code source, SQL, Python, YAML, notebooks, README)
et les schémas réels de sources de données connectées (BigQuery, PostgreSQL, GCS, Power BI).
Tu extrais des informations précises, détaillées et exploitables pour remplir chaque champ
d'une spécification technique. Tu n'inventes jamais d'informations absentes des sources.
Réponds toujours en JSON valide uniquement, sans texte supplémentaire ni markdown."""

DEEP_DIVE_SYSTEM_PROMPT = """Tu es un expert en rédaction de spécifications techniques data engineering.
Tu analyses du code source et des métadonnées de pipelines pour rédiger des sections détaillées.
Chaque section doit être complète, précise et directement utilisable dans un document professionnel.
Réponds uniquement en JSON valide."""

SYNTHESIS_SYSTEM_PROMPT = """Tu es un expert en spécifications techniques data engineering.
Tu révises et enrichis des valeurs extraites automatiquement pour les rendre cohérentes,
complètes et précises. Tu identifies les incohérences, les doublons et les lacunes.
Réponds uniquement en JSON valide."""

# ── Pass 1: section-batched extraction prompt ─────────────────────────────────

BATCH_EXTRACTION_PROMPT = """Tu dois extraire des informations précises depuis un repository pour remplir les champs suivants.

## Contexte du pipeline ciblé:
{pipeline_context}

## Fichiers de code pertinents pour cette section:
{relevant_files}

## Métadonnées générales du repository:
{base_metadata}

## Champs à remplir (section: {section_name}):
{fields_description}

## Instructions:
- Réponds UNIQUEMENT avec un objet JSON où les clés sont les "id" des champs.
- Pour type=text: réponse courte et précise (1-2 phrases max).
- Pour type=choice: UN SEUL choix parmi les options disponibles.
- Pour type=list: liste à puces en Markdown (- item).
- Pour type=paragraph: paragraphe structuré de 3-6 phrases avec des détails concrets tirés du code.
- Pour type=table: tableau Markdown complet avec toutes les colonnes et lignes pertinentes.
- Base-toi STRICTEMENT sur le contenu des fichiers fournis. N'invente pas.
- Si l'info est absente des sources, indique "Non identifié dans les sources analysées".

Format:
{{"field_id": "valeur extraite", ...}}
"""

# ── Pass 2: deep-dive prompt for thin paragraph/table answers ─────────────────

DEEP_DIVE_PROMPT = """Le champ suivant a une réponse insuffisante ou trop courte. Approfondis-la.

## Contexte du pipeline:
{pipeline_context}

## Champ à approfondir:
- id: {field_id}
- label: {field_label}
- section: {field_section}
- description: {field_description}
- type: {field_type}
- Réponse actuelle: {current_value}

## Fichiers de code disponibles (contenu complet):
{all_relevant_files}

## Instructions selon le type:
- paragraph: Rédige 4-8 phrases précises avec des exemples concrets tirés du code (noms de tables, fonctions, fichiers).
- table: Crée un tableau Markdown exhaustif avec toutes les colonnes pertinentes et autant de lignes que nécessaire.
- list: Fournis une liste complète avec au moins 5 items détaillés si possible.
- Cite les fichiers sources exacts quand tu le peux (ex: "dans pipeline_etl.py, la fonction X...").

Réponds UNIQUEMENT avec un JSON: {{"value": "contenu enrichi"}}
"""

# ── Pass 3: synthesis / coherence pass ───────────────────────────────────────

SYNTHESIS_PROMPT = """Tu révises les valeurs extraites automatiquement pour une spécification technique.
Assure-toi que les valeurs sont cohérentes entre elles, complètes et précises.

## Pipeline ciblé:
{pipeline_context}

## Toutes les valeurs extraites (à réviser):
{all_values_json}

## Champs de référence:
{fields_json}

## Instructions:
- Identifie les champs avec "Non identifié" et essaie de les inférer depuis les autres champs.
- Assure la cohérence (ex: les technologies mentionnées en section 1 doivent correspondre à celles en section 3).
- Enrichis les valeurs trop courtes pour les champs de type paragraph/table si possible.
- Ne change PAS les valeurs qui sont déjà bonnes — retourne-les telles quelles.
- Retourne UN objet JSON avec TOUS les field_ids (même ceux non modifiés).

Format: {{"field_id": "valeur finale", ...}}
"""


class ExtractionAgent:
    """Multi-pass chunked extraction: section-batched → deep-dive → synthesis."""

    BATCH_SIZE = 10          # fields per LLM call in pass 1
    MIN_PARAGRAPH_LEN = 120  # chars below which a paragraph answer is considered thin
    MIN_TABLE_ROWS = 1       # markdown table rows below which we deep-dive

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def extract(self, repo_metadata: dict, fields: list[dict]) -> dict[str, str]:
        """
        Three-pass extraction:
          1. Section-batched: group fields by section, focus context per section
          2. Deep-dive: re-extract thin paragraph/table answers
          3. Synthesis: cross-field coherence & gap-filling
        """
        if not fields:
            return {}

        pipeline_context = self._build_pipeline_context(repo_metadata)
        base_metadata    = self._build_base_metadata(repo_metadata)
        file_index       = self._build_file_index(repo_metadata)

        # ── Pass 1: section-batched extraction ──────────────────────────────
        extracted: dict[str, str] = {}
        section_groups = self._group_by_section(fields)

        for section_name, section_fields in section_groups.items():
            batches = [section_fields[i:i + self.BATCH_SIZE]
                       for i in range(0, len(section_fields), self.BATCH_SIZE)]
            for batch in batches:
                relevant = self._pick_relevant_files(section_name, batch, file_index)
                batch_result = self._run_batch(
                    section_name, batch, pipeline_context, base_metadata, relevant
                )
                extracted.update(batch_result)

        # Fill any missing field ids with placeholder
        for f in fields:
            if f["id"] not in extracted:
                extracted[f["id"]] = "Non identifié dans les sources analysées"

        # ── Pass 2: deep-dive for thin paragraph/table fields ───────────────
        all_files_text = self._build_all_files_text(file_index)
        fields_by_id = {f["id"]: f for f in fields}

        thin_fields = [
            f for f in fields
            if self._is_thin(extracted.get(f["id"], ""), f.get("type", "text"))
        ]

        for f in thin_fields:
            enriched = self._run_deep_dive(
                f, extracted.get(f["id"], ""), pipeline_context, all_files_text
            )
            if enriched and len(enriched) > len(extracted.get(f["id"], "")):
                extracted[f["id"]] = enriched

        # ── Pass 3: synthesis / coherence pass ─────────────────────────────
        extracted = self._run_synthesis(extracted, fields, pipeline_context)

        return extracted

    # ─────────────────────────────────────────────────────────────────────────
    # Pass 1 helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _group_by_section(self, fields: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for f in fields:
            sec = f.get("section", "Général") or "Général"
            groups.setdefault(sec, []).append(f)
        return groups

    def _run_batch(self, section_name: str, batch: list[dict],
                   pipeline_context: str, base_metadata: str,
                   relevant_files: str) -> dict[str, str]:
        fields_desc = self._format_fields(batch)
        prompt = BATCH_EXTRACTION_PROMPT.format(
            pipeline_context=pipeline_context,
            relevant_files=relevant_files or "Aucun fichier spécifique pour cette section.",
            base_metadata=base_metadata,
            section_name=section_name,
            fields_description=fields_desc,
        )
        raw = self.llm.generate(prompt, system_prompt=EXTRACTION_SYSTEM_PROMPT)
        field_ids = [f["id"] for f in batch]
        return self._parse_json_response(raw, field_ids)

    # ─────────────────────────────────────────────────────────────────────────
    # Pass 2 helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _is_thin(self, value: str, field_type: str) -> bool:
        if not value or value.strip() in ("", "Non identifié", "Non identifié dans les sources analysées"):
            return True
        if field_type == "paragraph" and len(value) < self.MIN_PARAGRAPH_LEN:
            return True
        if field_type == "table":
            rows = [l for l in value.split("\n") if l.strip().startswith("|")]
            if len(rows) <= self.MIN_TABLE_ROWS:
                return True
        if field_type == "list":
            items = [l for l in value.split("\n") if l.strip().startswith("-")]
            if len(items) < 2:
                return True
        return False

    def _run_deep_dive(self, field: dict, current_value: str,
                       pipeline_context: str, all_files_text: str) -> str:
        prompt = DEEP_DIVE_PROMPT.format(
            pipeline_context=pipeline_context,
            field_id=field["id"],
            field_label=field.get("label", ""),
            field_section=field.get("section", ""),
            field_description=field.get("description", ""),
            field_type=field.get("type", "text"),
            current_value=current_value or "Aucune valeur extraite",
            all_relevant_files=all_files_text[:12000],
        )
        raw = self.llm.generate(prompt, system_prompt=DEEP_DIVE_SYSTEM_PROMPT)
        parsed = self._parse_json_response(raw, ["value"])
        return parsed.get("value", current_value)

    # ─────────────────────────────────────────────────────────────────────────
    # Pass 3 helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _run_synthesis(self, extracted: dict[str, str], fields: list[dict],
                       pipeline_context: str) -> dict[str, str]:
        prompt = SYNTHESIS_PROMPT.format(
            pipeline_context=pipeline_context,
            all_values_json=json.dumps(extracted, ensure_ascii=False, indent=2)[:10000],
            fields_json=json.dumps(
                [{"id": f["id"], "label": f.get("label",""), "type": f.get("type","text"),
                  "section": f.get("section","")} for f in fields],
                ensure_ascii=False, indent=2
            )[:4000],
        )
        raw = self.llm.generate(prompt, system_prompt=SYNTHESIS_SYSTEM_PROMPT)
        field_ids = [f["id"] for f in fields]
        result = self._parse_json_response(raw, field_ids)
        # Only overwrite where synthesis produced a real improvement
        merged = dict(extracted)
        for fid, val in result.items():
            if val and val != "Non identifié dans les sources analysées":
                merged[fid] = val
        return merged

    # ─────────────────────────────────────────────────────────────────────────
    # Context builders
    # ─────────────────────────────────────────────────────────────────────────

    def _build_pipeline_context(self, metadata: dict) -> str:
        ctx = metadata.get("datasource_context", "")
        # datasource_context already contains the pipeline block injected by orchestrator
        if ctx:
            return ctx[:3000]
        return "Aucun pipeline spécifique fourni — analyse du repository global."

    def _build_base_metadata(self, metadata: dict) -> str:
        parts = [
            f"Repo: {metadata.get('repo_name', 'N/A')}",
            f"Owner: {metadata.get('owner', 'N/A')}",
            f"Description: {metadata.get('description', 'N/A')}",
            f"Langages: {metadata.get('languages', 'N/A')}",
            f"Topics: {metadata.get('topics', 'N/A')}",
        ]
        if metadata.get("readme"):
            parts.append(f"\n## README:\n{metadata['readme'][:4000]}")
        if metadata.get("structure"):
            files = [f["path"] for f in metadata["structure"].get("files", [])]
            parts.append(f"\n## Fichiers ({len(files)}):\n{json.dumps(files[:120], ensure_ascii=False)}")
        return "\n".join(parts)

    def _build_file_index(self, metadata: dict) -> dict[str, list[dict]]:
        """Build a dict: file_type → list of {path, content} dicts."""
        return {
            "sql":      metadata.get("sql_files", []),
            "python":   metadata.get("python_files", []),
            "yaml":     metadata.get("yaml_files", []),
            "json":     metadata.get("json_files", []),
            "notebook": metadata.get("notebook_files", []),
        }

    def _build_all_files_text(self, file_index: dict) -> str:
        parts = []
        limits = {"sql": 3000, "python": 3000, "yaml": 1500, "json": 1500, "notebook": 2000}
        labels = {"sql": "SQL", "python": "Python", "yaml": "YAML", "json": "JSON", "notebook": "Notebook"}
        for ftype, files in file_index.items():
            for f in files[:6]:  # at most 6 files per type for deep dive
                lim = limits.get(ftype, 2000)
                parts.append(f"### [{labels[ftype]}] {f.get('path','')}\n{f.get('content','')[:lim]}")
        return "\n\n".join(parts)

    def _pick_relevant_files(self, section_name: str, fields: list[dict],
                              file_index: dict) -> str:
        """Select files most relevant to this section based on keyword heuristics."""
        sec_lower = section_name.lower()
        field_labels = " ".join(f.get("label","") + " " + f.get("description","") for f in fields).lower()
        combined = sec_lower + " " + field_labels

        # Keyword → file type mapping
        prefer_sql      = any(k in combined for k in ["source", "table", "schema", "requête", "query",
                                                       "données", "data", "lineage", "champ", "colonne"])
        prefer_python   = any(k in combined for k in ["transformation", "traitement", "etl", "pipeline",
                                                       "processus", "orchestration", "script", "job"])
        prefer_yaml     = any(k in combined for k in ["config", "paramètre", "déploiement", "airflow",
                                                       "dbt", "schedule", "trigger"])
        prefer_notebook = any(k in combined for k in ["analyse", "exploration", "visualisation", "notebook"])

        parts = []
        lim = 3000

        if prefer_sql:
            for f in file_index.get("sql", [])[:4]:
                parts.append(f"### [SQL] {f.get('path','')}\n```sql\n{f.get('content','')[:lim]}\n```")
        if prefer_python:
            for f in file_index.get("python", [])[:4]:
                parts.append(f"### [Python] {f.get('path','')}\n```python\n{f.get('content','')[:lim]}\n```")
        if prefer_yaml:
            for f in file_index.get("yaml", [])[:3]:
                parts.append(f"### [YAML] {f.get('path','')}\n```yaml\n{f.get('content','')[:1500]}\n```")
        if prefer_notebook:
            for f in file_index.get("notebook", [])[:2]:
                parts.append(f"### [Notebook] {f.get('path','')}\n{f.get('content','')[:2000]}")

        # Fallback: include at least one SQL and one Python file
        if not parts:
            for f in file_index.get("sql", [])[:2]:
                parts.append(f"### [SQL] {f.get('path','')}\n```sql\n{f.get('content','')[:lim]}\n```")
            for f in file_index.get("python", [])[:2]:
                parts.append(f"### [Python] {f.get('path','')}\n```python\n{f.get('content','')[:lim]}\n```")

        return "\n\n".join(parts) if parts else ""

    # ─────────────────────────────────────────────────────────────────────────
    # Formatting helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _format_fields(self, fields: list[dict]) -> str:
        lines = []
        for f in fields:
            parts = [f'- id="{f["id"]}" | label="{f.get("label","")}"']
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

    def _parse_json_response(self, raw: str, field_ids: list[str]) -> dict[str, str]:
        raw = raw.strip()
        # Strip code fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
        # Some models wrap with extra text before JSON
        brace = raw.find("{")
        if brace > 0:
            raw = raw[brace:]
        last_brace = raw.rfind("}")
        if last_brace >= 0:
            raw = raw[:last_brace + 1]
        try:
            data = json.loads(raw)
            return {fid: str(data[fid]) for fid in field_ids if fid in data}
        except json.JSONDecodeError:
            return {}

    # ─────────────────────────────────────────────────────────────────────────
    # Legacy helper kept for backward compatibility (used in old routes)
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_metadata_summary(self, metadata: dict) -> str:
        return self._build_base_metadata(metadata)
