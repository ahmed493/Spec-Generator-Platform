"""
MappingAgent — Deterministic Structured Composition
====================================================
Builds the final specification document directly from the structured
placeholders + extracted values, instead of trying to fill a garbled
PDF-extracted template verbatim.

Why deterministic (no LLM):
  - No extracted detail can be silently dropped or hallucinated.
  - Every field is rendered exactly once, in a fixed logical section → no
    duplicated sections, no contradictions.
  - Fast and fully reproducible (no API latency / timeouts).

Rendering rules:
  - Fields are grouped into ordered logical sections by id (exact list or prefix).
  - `evaluation_criteria` (a nested JSON mega-field) is decomposed: any sub-key
    that duplicates a populated dedicated field is suppressed; unique sub-keys
    (e.g. Technologies, SQL table structure) are surfaced — never as raw JSON.
  - List-of-dict values render as Markdown tables; list values as bullet lists.
  - Missing / NOT_FOUND values render as "[À compléter]".
"""
import json
import re
from typing import Optional, Any

from app.agents.llm_client import BaseLLMClient

# ── Values that mean "not filled" ───────────────────────────────────────────
_EMPTY_VALUES = frozenset({
    "", "not_found", "non identifié", "non identifié dans les sources analysées",
    "none", "null", "n/a", "na", "à compléter", "[à compléter]", "a compléter",
    "[a compléter]", "à renseigner", "-", "—", "...", "…", "?", "vide",
})

_TODO = "[À compléter]"

# ── French stop-words for fuzzy label matching ──────────────────────────────
_STOPWORDS_FR = frozenset({
    "de", "du", "la", "le", "les", "des", "un", "une", "et", "ou", "en", "d",
    "l", "au", "aux", "par", "pour", "avec", "sur", "dans", "est", "sont", "a",
})

# ── Header / meta fields (rendered as a header table, with clean labels) ─────
_META_IDS = [
    "project", "writer", "recipients", "date_written", "validation_date",
    "budget_code", "version", "author", "history",
]
_META_LABELS = {
    "project": "Projet",
    "writer": "Rédaction",
    "recipients": "Destinataire(s)",
    "date_written": "Date de rédaction",
    "validation_date": "Validation / Date",
    "budget_code": "Code budgétaire",
    "version": "Version",
    "author": "Auteur",
    "history": "Historique",
}

# ── Ordered logical section plan ────────────────────────────────────────────
# Each entry: (title, selector). A selector assigns fields by exact id or by
# id prefix. `eval` marks the section that hosts decomposed evaluation_criteria.
_SECTION_PLAN: list[tuple[str, dict]] = [
    ("Critère d'évaluation de la demande", {"eval": True}),
    ("Description du besoin", {"ids": ["general_need_description"]}),
    ("Traitement", {"ids": [
        "sensitive_data_requirements", "historization_requirements",
        "error_handling", "rejection_handling", "data_provisioning",
        "exploitation_details", "observability_requirements",
    ]}),
    ("Interface(s) d'entrée", {"prefixes": ["input_interface_", "interface_entree_"]}),
    ("Interface(s) de sortie", {"prefixes": ["output_interface_", "interface_sortie_"]}),
    ("Structure de l'interface", {"prefixes": ["structure_interface_"]}),
]

# evaluation_criteria sub-keys we always skip (richer dedicated rendering exists)
_EVAL_SKIP_KEYS = frozenset({"mapping"})


class MappingAgent:
    """Deterministic structured spec composition."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        # Kept for API compatibility; composition no longer requires an LLM.
        self.llm = llm_client

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
        """Render a clean, complete specification from structured values."""
        fields = fields or []
        id_to_field = {f["id"]: f for f in fields if f.get("id")}
        # label → value; on duplicate labels keep the first populated value so
        # a populated dedicated field isn't masked by an empty namesake.
        label_to_value: dict[str, str] = {}
        for f in fields:
            if not f.get("id"):
                continue
            lbl = f.get("label", f["id"])
            val = extracted_values.get(f["id"], "")
            if lbl not in label_to_value or self._is_empty(label_to_value[lbl]):
                label_to_value[lbl] = val

        # Assign every field to exactly one section (no duplication).
        assigned: dict[str, list[str]] = {title: [] for title, _ in _SECTION_PLAN}
        used: set[str] = set(_META_IDS)  # meta handled separately

        for fid in (f["id"] for f in fields if f.get("id")):
            if fid in used or fid == "evaluation_criteria":
                continue
            section = self._section_for(fid)
            if section:
                assigned[section].append(fid)
                used.add(fid)

        # Leftover fields: tables → "Mapping des champs"; scalars → "Autres".
        mapping_fields: list[str] = []
        other_fields: list[str] = []
        for f in fields:
            fid = f.get("id")
            if not fid or fid in used or fid == "evaluation_criteria":
                continue
            if self._is_table_value(extracted_values.get(fid, "")):
                mapping_fields.append(fid)
            else:
                other_fields.append(fid)
            used.add(fid)

        # ── Build the document ──────────────────────────────────────────────
        project_name = self._clean(extracted_values.get("project", "")) or "Spécification"
        parts: list[str] = [f"# Expression de besoin — {project_name}", ""]
        parts.append(self._render_header(extracted_values))

        n = 1
        for title, selector in _SECTION_PLAN:
            if selector.get("eval"):
                body = self._render_eval_section(extracted_values, label_to_value)
            else:
                body = self._render_fields(assigned[title], id_to_field, extracted_values)
            if body.strip():
                parts.append(f"\n## {n}. {title}\n\n{body.rstrip()}")
                n += 1

        if mapping_fields:
            body = self._render_fields(mapping_fields, id_to_field, extracted_values)
            if body.strip():
                parts.append(f"\n## {n}. Mapping des champs\n\n{body.rstrip()}")
                n += 1

        if other_fields:
            body = self._render_fields(other_fields, id_to_field, extracted_values)
            if body.strip():
                parts.append(f"\n## {n}. Autres informations\n\n{body.rstrip()}")
                n += 1

        return "\n".join(parts).strip() + "\n"

    # ─────────────────────────────────────────────────────────────────────────
    # Section assignment
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _section_for(fid: str) -> Optional[str]:
        for title, selector in _SECTION_PLAN:
            if fid in selector.get("ids", []):
                return title
        for title, selector in _SECTION_PLAN:
            for prefix in selector.get("prefixes", []):
                if fid.startswith(prefix):
                    return title
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Rendering
    # ─────────────────────────────────────────────────────────────────────────

    def _render_header(self, values: dict[str, str]) -> str:
        rows = ["| Champ | Valeur |", "|---|---|"]
        for fid in _META_IDS:
            label = _META_LABELS.get(fid, fid)
            val = values.get(fid, "")
            cell = _TODO if self._is_empty(val) else self._cell(self._clean(val))
            rows.append(f"| {self._cell(label)} | {cell} |")
        return "\n".join(rows)

    def _render_fields(
        self, ids: list[str], id_to_field: dict[str, dict], values: dict[str, str]
    ) -> str:
        chunks: list[str] = []
        for fid in ids:
            field = id_to_field.get(fid, {})
            label = field.get("label") or fid
            chunks.append(self._render_field(label, values.get(fid, "")))
        return "\n\n".join(c for c in chunks if c)

    def _render_field(self, label: str, raw: Any) -> str:
        """Render one labelled value as Markdown (scalar / bullets / table)."""
        parsed = self._parse(raw)

        # List of dicts → table
        if isinstance(parsed, list) and parsed and all(isinstance(x, dict) for x in parsed):
            table = self._dicts_to_table(parsed)
            return f"**{label}** :\n\n{table}" if table else f"**{label}** : {_TODO}"

        # List of scalars → bullets
        if isinstance(parsed, list):
            items = [self._clean(x) for x in parsed if not self._is_empty(x)]
            if not items:
                return f"**{label}** : {_TODO}"
            bullets = "\n".join(f"- {self._inline(i)}" for i in items)
            return f"**{label}** :\n{bullets}"

        # Dict → definition bullets
        if isinstance(parsed, dict):
            lines = [
                f"- **{self._inline(str(k))}** : {self._inline(self._clean(v))}"
                for k, v in parsed.items() if not self._is_empty(v)
            ]
            if not lines:
                return f"**{label}** : {_TODO}"
            return f"**{label}** :\n" + "\n".join(lines)

        # Scalar
        if self._is_empty(parsed):
            return f"**{label}** : {_TODO}"
        return f"**{label}** : {self._inline(self._clean(parsed))}"

    def _render_eval_section(
        self, values: dict[str, str], label_to_value: dict[str, str]
    ) -> str:
        """Decompose evaluation_criteria: surface only sub-keys that aren't
        already covered by a populated dedicated field."""
        parsed = self._parse(values.get("evaluation_criteria", ""))
        if not isinstance(parsed, dict):
            return ""

        chunks: list[str] = []
        for key, val in parsed.items():
            if self._norm(key) in _EVAL_SKIP_KEYS:
                continue
            if self._is_empty(val):
                continue
            # Suppress if a dedicated field already covers this (avoid dup/conflict)
            if self._has_populated_dedicated(key, label_to_value):
                continue
            chunks.append(self._render_field(key, val))
        return "\n\n".join(c for c in chunks if c)

    def _has_populated_dedicated(self, key: str, label_to_value: dict[str, str]) -> bool:
        """True if a dedicated field whose label matches `key` has a real value."""
        nk = self._norm(key)
        # exact / substring
        for lbl, val in label_to_value.items():
            nl = self._norm(lbl)
            if nk == nl or (len(nk) >= 4 and len(nl) >= 4 and (nk in nl or nl in nk)):
                return not self._is_empty(val)
        # word overlap (≥2 meaningful words)
        kw = self._words(nk)
        for lbl, val in label_to_value.items():
            if len(kw & self._words(self._norm(lbl))) >= 2:
                return not self._is_empty(val)
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Table building
    # ─────────────────────────────────────────────────────────────────────────

    def _dicts_to_table(self, rows: list[dict]) -> str:
        # Column order = first-seen order across all rows
        cols: list[str] = []
        for r in rows:
            for k in r.keys():
                if k not in cols:
                    cols.append(k)
        if not cols:
            return ""
        out = ["| " + " | ".join(self._cell(c) for c in cols) + " |",
               "|" + "|".join("---" for _ in cols) + "|"]
        for r in rows:
            cells = []
            for c in cols:
                v = r.get(c, "")
                cells.append(self._cell(self._clean(v)) if not self._is_empty(v) else "—")
            out.append("| " + " | ".join(cells) + " |")
        return "\n".join(out)

    # ─────────────────────────────────────────────────────────────────────────
    # Value helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse(raw: Any) -> Any:
        """Parse JSON-encoded strings into Python objects; pass through otherwise."""
        if not isinstance(raw, str):
            return raw
        s = raw.strip()
        if s[:1] in ("[", "{"):
            try:
                return json.loads(s)
            except (json.JSONDecodeError, ValueError):
                return raw
        return raw

    def _is_table_value(self, raw: Any) -> bool:
        parsed = self._parse(raw)
        return isinstance(parsed, list) and bool(parsed) and all(isinstance(x, dict) for x in parsed)

    @staticmethod
    def _is_empty(v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, (list, dict)):
            return len(v) == 0
        return str(v).strip().lower() in _EMPTY_VALUES

    @staticmethod
    def _clean(v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @staticmethod
    def _inline(s: str) -> str:
        """Collapse newlines so a value stays on its line."""
        return re.sub(r"\s*\n\s*", " ", str(s)).strip()

    @staticmethod
    def _cell(s: str) -> str:
        """Escape a value for use inside a Markdown table cell."""
        return re.sub(r"\s*\n\s*", " ", str(s)).replace("|", r"\|").strip()

    @staticmethod
    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", str(s).lower().strip())

    @staticmethod
    def _words(s: str) -> set:
        return set(re.split(r"\W+", s)) - _STOPWORDS_FR - {""}
