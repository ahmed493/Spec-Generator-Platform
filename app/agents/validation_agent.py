"""
ValidationAgent
- Checks that all detected template fields have been filled
- Flags missing, empty, or placeholder-like values ("Non identifié")
- Returns a structured validation report
"""


class ValidationAgent:
    """Validates that all detected template fields have been properly filled."""

    MISSING_INDICATORS = {"non identifié", "n/a", "", "[missing", "non identifie"}

    def validate(self, fields: list[dict], filled_values: dict[str, str]) -> dict:
        """
        fields: list of {id, label, section, description, type, required, options}
        filled_values: {field_id: value}

        Returns:
        - is_valid: bool (True if all required fields are filled)
        - filled: list of filled field ids
        - missing: list of unfilled field ids (required only)
        - warnings: list of field ids with suspicious values
        - report: human-readable summary
        """
        filled = []
        missing = []
        warnings = []

        for field in fields:
            fid = field["id"]
            label = field.get("label", fid)
            required = field.get("required", True)
            value = filled_values.get(fid, "")
            lower_val = value.strip().lower()

            if not lower_val or any(lower_val.startswith(ind) for ind in self.MISSING_INDICATORS):
                if required:
                    missing.append(f"{fid} ({label})")
                else:
                    warnings.append(f"{fid} ({label}) [optionnel]")
            elif len(value.strip()) < 5:
                warnings.append(f"{fid} ({label})")
                filled.append(fid)
            else:
                filled.append(fid)

        total = len(fields)
        is_valid = len(missing) == 0
        report_lines = [
            f"Champs remplis ({len(filled)}/{total})",
        ]
        if missing:
            report_lines.append(f"Champs manquants ({len(missing)}): {', '.join(missing)}")
        if warnings:
            report_lines.append(f"Champs suspects ({len(warnings)}): {', '.join(warnings)}")
        if is_valid:
            report_lines.append("Validation réussie: tous les champs requis sont remplis.")
        else:
            report_lines.append("Validation échouée: certains champs requis sont manquants.")

        return {
            "is_valid": is_valid,
            "filled": filled,
            "missing": missing,
            "warnings": warnings,
            "report": "\n".join(report_lines),
        }
