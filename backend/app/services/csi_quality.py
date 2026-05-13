"""
CSI Quality / Lifecycle Engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared, stateless functions for computing claim quality metrics and lifecycle
status.  Intentionally import-safe: this module does NOT import from
csi_research_engine, preventing circular dependencies.

Public surface:
    classify_source_tier(url, policy) -> str
    calibrate_confidence(claim, reviews, contradictions, policy) -> float
    compute_claim_status(claim, reviews, contradictions, policy) -> str
    recompute_claim_quality(store, simulation_id, claim_id, policy) -> dict
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..utils.logger import get_logger

logger = get_logger("mirofish.csi_quality")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to the closed interval [lo, hi]."""
    return max(lo, min(hi, value))


def _is_url(text: str) -> bool:
    """Return True when *text* looks like an HTTP/HTTPS URL."""
    return text.startswith("http://") or text.startswith("https://")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def classify_source_tier(url: str, policy: Any) -> str:
    """Return 'tier1', 'tier2', or 'tier3' for *url* based on *policy*.

    Resolution order:
    1. Exact domain match against policy.provenance.allowed_domains  -> tier1
    2. TLD ends with .gov or .edu                                    -> tier2
    3. Everything else                                               -> tier3

    Non-HTTP strings (bare IDs, etc.) fall through to tier3.
    """
    if not _is_url(url):
        return "tier3"

    # Strip scheme and extract hostname
    without_scheme = url.split("://", 1)[-1]
    hostname = without_scheme.split("/")[0].lower()

    # Tier 1: exact match in policy's allowed_domains
    allowed: List[str] = list(policy.provenance.allowed_domains or [])
    if hostname in allowed or any(hostname.endswith("." + d) for d in allowed):
        return "tier1"

    # Tier 2: government or academic TLD
    if hostname.endswith(".gov") or hostname.endswith(".edu"):
        return "tier2"

    return "tier3"


def calibrate_confidence(
    claim: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    contradictions: List[Dict[str, Any]],
    policy: Any,
) -> float:
    """Compute a deterministic confidence score in [0.0, 1.0].

    raw = evidence_quality * evidence_count_factor * review_agreement * contradiction_penalty

    evidence_quality      avg tier weight of source URLs (default 0.3 for non-URL / unknown).
    evidence_count_factor min(1.0, unique_sources / required_evidence_count).
    review_agreement      supports / total_reviews; 0.5 when no reviews.
    contradiction_penalty 0.5 if any contradiction.status == 'open', else 1.0.
    """
    tier_weights: Dict[str, float] = dict(policy.provenance.tier_weights or {})

    # --- evidence quality ---
    source_ids: List[str] = list(claim.get("source_ids") or [])
    unique_sources: List[str] = list(dict.fromkeys(source_ids))  # preserve order, dedupe

    if unique_sources:
        weight_sum = 0.0
        for src in unique_sources:
            tier = classify_source_tier(src, policy)
            weight_sum += tier_weights.get(tier, 0.3)
        evidence_quality = weight_sum / len(unique_sources)
    else:
        evidence_quality = 0.3  # default tier3 weight

    # --- evidence count factor ---
    required: int = max(1, int(policy.claims.required_evidence_count))
    evidence_count_factor = min(1.0, len(unique_sources) / required)

    # --- review agreement ---
    total_reviews = len(reviews)
    if total_reviews == 0:
        review_agreement = 0.5
    else:
        supports = sum(1 for r in reviews if r.get("verdict") == "supports")
        review_agreement = supports / total_reviews

    # --- contradiction penalty ---
    open_contradictions = [
        c for c in contradictions if c.get("status") == "open"
    ]
    contradiction_penalty = 0.5 if open_contradictions else 1.0

    raw = evidence_quality * evidence_count_factor * review_agreement * contradiction_penalty
    return round(_clamp(raw, 0.0, 1.0), 3)


def compute_claim_status(
    claim: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    contradictions: List[Dict[str, Any]],
    policy: Any,
) -> str:
    """Determine the lifecycle status string for *claim*.

    Returns one of: 'proposed', 'under_review', 'needs_revision',
                    'contested', 'revised', 'validated'

    Priority order: validated > contested > needs_revision > revised > under_review > proposed.
    'validated' requires: reviews >= min_reviews, support_ratio >= support_threshold,
    unique_sources >= required_evidence_count, confidence >= auto_validate_threshold,
    and no open contradictions.
    """
    open_contradictions = [
        c for c in contradictions if c.get("status") == "open"
    ]
    total_reviews = len(reviews)
    unique_sources = list(dict.fromkeys(claim.get("source_ids") or []))

    # Validated: all strict conditions must pass
    if total_reviews >= policy.reviews.min_reviews_per_claim:
        supports = sum(1 for r in reviews if r.get("verdict") == "supports")
        support_ratio = supports / total_reviews if total_reviews else 0.0
        confidence = calibrate_confidence(claim, reviews, contradictions, policy)
        if (
            support_ratio >= policy.verdicts.support_threshold
            and len(unique_sources) >= policy.claims.required_evidence_count
            and confidence >= policy.claims.auto_validate_threshold
            and not open_contradictions
        ):
            return "validated"

    # Contested: open contradictions present
    if open_contradictions:
        return "contested"

    # Needs revision: any reviewer flagged it
    if any(r.get("verdict") == "needs_revision" for r in reviews):
        return "needs_revision"

    # Revised: was previously marked for revision and has been updated
    if claim.get("is_revision") is True or claim.get("parent_claim_id") is not None:
        return "revised"

    # Under review: some reviews but not enough
    if total_reviews > 0:
        return "under_review"

    # Default
    return "proposed"


def recompute_claim_quality(
    store: Any,
    simulation_id: str,
    claim_id: str,
    policy: Any,
) -> Dict[str, Any]:
    """Read current state from *store*, recompute quality for *claim_id*, and
    record a CLAIM_STATUS_UPDATED agent action.

    Returns {"claim_id": str, "new_status": str, "new_confidence": float}.
    Returns {} when the claim cannot be located.
    """
    if not claim_id:
        return {}

    snapshot = store.build_blackboard_snapshot(simulation_id)
    claims_map: Dict[str, Any] = snapshot.get("claims") or {}
    claim = claims_map.get(claim_id)

    if claim is None:
        logger.debug(
            "recompute_claim_quality: claim %s not found in simulation %s",
            claim_id,
            simulation_id,
        )
        return {}

    # Reviews are embedded on the claim by build_blackboard_snapshot
    reviews: List[Dict[str, Any]] = list(claim.get("reviews") or [])

    # Contradictions relevant to this claim (keyed dict of all contradictions)
    all_contradictions: Dict[str, Any] = snapshot.get("contradictions") or {}
    contradictions: List[Dict[str, Any]] = [
        c
        for c in all_contradictions.values()
        if c.get("claim_id") == claim_id or claim_id in (c.get("claim_ids") or [])
    ]

    old_status: str = claim.get("status", "proposed")
    old_confidence: float = float(claim.get("confidence", 0.0))

    new_confidence = calibrate_confidence(claim, reviews, contradictions, policy)
    new_status = compute_claim_status(claim, reviews, contradictions, policy)

    # Append-only lifecycle event so the effective snapshot can patch reads.
    if hasattr(store, "update_claim_lifecycle"):
        try:
            store.update_claim_lifecycle(
                simulation_id=simulation_id,
                claim_id=claim_id,
                old_status=old_status,
                new_status=new_status,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
            )
        except Exception as _le:  # pragma: no cover - defensive
            logger.debug("update_claim_lifecycle failed for %s: %s", claim_id, _le)

    # Also rewrite the raw claims.jsonl row so reports / analytics that bypass
    # the effective snapshot (e.g. open the bundle directly) see calibrated values
    # rather than LLM-stated round numbers (0.7, 0.85, 0.92).
    if hasattr(store, "update_claim_fields"):
        try:
            store.update_claim_fields(
                simulation_id,
                claim_id,
                {"confidence": float(new_confidence), "status": new_status},
            )
        except Exception as _ue:  # pragma: no cover - defensive
            logger.debug("update_claim_fields failed for %s: %s", claim_id, _ue)

    store.record_agent_action(simulation_id, {
        "action_type": "CLAIM_STATUS_UPDATED",
        "detail": {
            "claim_id": claim_id,
            "old_status": old_status,
            "new_status": new_status,
            "old_confidence": old_confidence,
            "new_confidence": new_confidence,
        },
    })

    logger.debug(
        "recompute_claim_quality: %s  status %s -> %s  confidence %.3f -> %.3f",
        claim_id,
        old_status,
        new_status,
        old_confidence,
        new_confidence,
    )

    return {
        "claim_id": claim_id,
        "new_status": new_status,
        "new_confidence": new_confidence,
    }
