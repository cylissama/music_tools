"""Purpose: Compare canonical metadata objects and generate safe dry-run reports."""

from __future__ import annotations

from typing import Any

from services.tagging.schema import CanonicalTrack, DiffReport, FieldDiff


def build_diff_report(
    before: CanonicalTrack,
    after: CanonicalTrack,
    *,
    review_required: bool = False,
    reasons: list[str] | None = None,
    auto_apply_confidence: float | None = None,
) -> DiffReport:
    """Create a structured diff between two canonical track states."""
    before_flat = _flatten("", before.to_dict())
    after_flat = _flatten("", after.to_dict())

    changes: list[FieldDiff] = []
    for field_path in sorted(set(before_flat) | set(after_flat)):
        before_value = before_flat.get(field_path)
        after_value = after_flat.get(field_path)
        if before_value != after_value:
            changes.append(FieldDiff(field_path=field_path, before=before_value, after=after_value))

    return DiffReport(
        file_path=after.file_path,
        changes=changes,
        review_required=review_required,
        reasons=reasons or [],
        auto_apply_confidence=auto_apply_confidence,
    )


def _flatten(prefix: str, value: Any) -> dict[str, Any]:
    """Flatten nested dataclass-like dictionaries into dotted paths."""
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten(next_prefix, item))
        return flattened

    if isinstance(value, list):
        return {prefix: value}

    return {prefix: value}
