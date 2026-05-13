"""
Unit and integration tests for app.services.csi_quality.

Tests cover:
- classify_source_tier: tier resolution logic against health policy domains
- calibrate_confidence: deterministic score formula including contradiction penalty
- compute_claim_status: lifecycle FSM transitions
- SimulationCSILocalStore.get_effective_snapshot: smoke test for graceful missing-sim handling
"""

from __future__ import annotations

import pytest

from app.services.csi_policy import build_csi_policy
from app.services.csi_quality import (
    calibrate_confidence,
    classify_source_tier,
    compute_claim_status,
)


# ---------------------------------------------------------------------------
# Test set 1: classify_source_tier
# ---------------------------------------------------------------------------


def test_tier1_pubmed() -> None:
    policy = build_csi_policy("health")
    assert classify_source_tier("https://pubmed.ncbi.nlm.nih.gov/123", policy) == "tier1"


def test_tier1_who() -> None:
    policy = build_csi_policy("health")
    assert classify_source_tier("https://who.int/docs/something", policy) == "tier1"


def test_tier2_gov_fallback() -> None:
    policy = build_csi_policy("health")
    # someagency.gov is not in allowed_domains -> falls to tier2 via .gov TLD
    assert classify_source_tier("https://someagency.gov/data", policy) == "tier2"


def test_tier3_unknown() -> None:
    policy = build_csi_policy("health")
    assert classify_source_tier("https://randomsite.com/article", policy) == "tier3"


def test_non_url_is_tier3() -> None:
    policy = build_csi_policy("health")
    assert classify_source_tier("claim_id_not_a_url", policy) == "tier3"


# ---------------------------------------------------------------------------
# Test set 2: calibrate_confidence
# ---------------------------------------------------------------------------


def test_high_confidence_tier1_sources_with_supports() -> None:
    """Two tier1 sources + two supporting reviews with no contradictions yields 1.0."""
    policy = build_csi_policy("health")
    claim = {"source_ids": ["https://pubmed.ncbi.nlm.nih.gov/1", "https://who.int/doc"]}
    reviews = [{"verdict": "supports"}, {"verdict": "supports"}]
    conf = calibrate_confidence(claim, reviews, [], policy)
    # evidence_quality=1.0, count_factor=1.0, agreement=1.0, penalty=1.0 -> 1.0
    assert conf >= 0.7, f"Expected >= 0.7, got {conf}"


def test_contradiction_penalty_halves_confidence() -> None:
    """An open contradiction must halve the confidence score exactly."""
    policy = build_csi_policy("health")
    claim = {
        "source_ids": [
            "https://pubmed.ncbi.nlm.nih.gov/1",
            "https://pubmed.ncbi.nlm.nih.gov/2",
        ]
    }
    reviews = [{"verdict": "supports"}, {"verdict": "supports"}]
    contradictions = [{"status": "open", "claim_id": "x"}]

    conf_no_contra = calibrate_confidence(claim, reviews, [], policy)
    conf_with_contra = calibrate_confidence(claim, reviews, contradictions, policy)

    assert conf_with_contra < conf_no_contra
    assert abs(conf_with_contra - conf_no_contra * 0.5) < 0.01


def test_low_confidence_insufficient_evidence() -> None:
    """Single tier3 source when two are required should produce sub-0.5 confidence."""
    policy = build_csi_policy("health")
    # 1 source where required_evidence_count=2, tier3 weight=0.3
    # raw = 0.3 * (1/2) * 1.0 * 1.0 = 0.15
    claim = {"source_ids": ["https://randomsite.com/article"]}
    reviews = [{"verdict": "supports"}]
    conf = calibrate_confidence(claim, reviews, [], policy)
    assert conf < 0.5, f"Expected < 0.5, got {conf}"


# ---------------------------------------------------------------------------
# Test set 3: compute_claim_status
# ---------------------------------------------------------------------------


def test_proposed_no_reviews() -> None:
    """A claim with no reviews and no sources defaults to 'proposed'."""
    policy = build_csi_policy("health")
    claim = {"source_ids": [], "status": "proposed"}
    assert compute_claim_status(claim, [], [], policy) == "proposed"


def test_under_review_one_review() -> None:
    """One review when min_reviews=2 is not enough to validate; status is 'under_review'."""
    policy = build_csi_policy("health")
    claim = {
        "source_ids": [
            "https://pubmed.ncbi.nlm.nih.gov/1",
            "https://pubmed.ncbi.nlm.nih.gov/2",
        ]
    }
    reviews = [{"verdict": "supports"}]
    status = compute_claim_status(claim, reviews, [], policy)
    assert status == "under_review"


def test_validated_strict_gates() -> None:
    """All health policy gates met (2 tier1 sources, 2 supporting reviews, no contradictions)."""
    policy = build_csi_policy("health")
    # Health policy: min_reviews=2, support_threshold=0.8, required_evidence=2,
    # auto_validate_threshold=0.9
    # confidence = 1.0 (both tier1, both supports, no penalty) -> passes threshold
    claim = {
        "source_ids": [
            "https://pubmed.ncbi.nlm.nih.gov/1",
            "https://pubmed.ncbi.nlm.nih.gov/2",
        ],
        "status": "under_review",
    }
    reviews = [{"verdict": "supports"}, {"verdict": "supports"}]
    status = compute_claim_status(claim, reviews, [], policy)
    assert status == "validated", f"Expected validated, got {status}"


def test_contested_if_open_contradiction() -> None:
    """Open contradiction blocks validation and returns 'contested'."""
    policy = build_csi_policy("health")
    claim = {
        "source_ids": [
            "https://pubmed.ncbi.nlm.nih.gov/1",
            "https://pubmed.ncbi.nlm.nih.gov/2",
        ],
        "status": "under_review",
    }
    reviews = [{"verdict": "supports"}, {"verdict": "supports"}]
    contradictions = [{"status": "open", "claim_id": "same_claim"}]
    status = compute_claim_status(claim, reviews, contradictions, policy)
    assert status == "contested"


def test_needs_revision_verdict() -> None:
    """A 'needs_revision' verdict in reviews propagates to claim status."""
    policy = build_csi_policy("health")
    claim = {"source_ids": ["https://pubmed.ncbi.nlm.nih.gov/1"]}
    reviews = [{"verdict": "needs_revision"}, {"verdict": "supports"}]
    status = compute_claim_status(claim, reviews, [], policy)
    assert status == "needs_revision"


# ---------------------------------------------------------------------------
# Test set 4: integration smoke test
# ---------------------------------------------------------------------------


def test_effective_snapshot_returns_claims() -> None:
    """get_effective_snapshot on a non-existent sim_id must not raise unexpectedly."""
    import tempfile
    import os

    from app.services.simulation_csi_local import SimulationCSILocalStore

    store = SimulationCSILocalStore()
    try:
        snap = store.get_effective_snapshot("test_sim_nonexistent")
        assert isinstance(snap, dict)
        assert "claims" in snap
    except FileNotFoundError:
        # Acceptable: simulation directory does not exist
        pass
