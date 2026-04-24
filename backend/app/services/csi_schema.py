"""Shared CSI artifact vocabulary."""

VALID_VERDICTS = {"supports", "contradicts", "needs_revision"}


def relation_type_for_verdict(verdict: str) -> str:
    normalized = (verdict or "").strip().lower()
    if normalized == "supports":
        return "supports"
    if normalized == "contradicts":
        return "contradicts"
    return "needs_revision"
