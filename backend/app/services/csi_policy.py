from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Any
from enum import Enum

class CSIMode(str, Enum):
    DEEP_RESEARCH = "deepresearch"
    HEALTH = "health"

class WorkflowType(str, Enum):
    BLACKBOARD = "blackboard"
    SEQUENTIAL = "sequential" # Legacy support

@dataclass
class PolicyBase:
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class RoleContract(PolicyBase):
    role_id: str
    allowed_actions: List[str]
    required_task_types: List[str]
    disallowed_task_types: List[str]
    evidence_obligations: int
    mandatory_review_coverage: bool = False
    synthesis_eligibility: bool = False
    description: str = ""

@dataclass
class ClaimPolicy(PolicyBase):
    required_evidence_count: int
    allow_unsupported: bool
    requires_cross_specialty_review: bool
    auto_validate_threshold: float

@dataclass
class ReviewPolicy(PolicyBase):
    min_reviews_per_claim: int
    require_opposing_role: bool
    allow_self_review: bool = False

@dataclass
class VerdictPolicy(PolicyBase):
    support_threshold: float
    contradiction_threshold: float
    auto_resolve_contradictions: bool

@dataclass
class ProvenancePolicy(PolicyBase):
    strict_domain_validation: bool
    allowed_domains: List[str] = field(default_factory=list)
    tier_weights: Dict[str, float] = field(default_factory=dict)

@dataclass
class GatePolicy(PolicyBase):
    max_rounds: int
    max_no_progress_cycles: int
    min_claims_for_synthesis: int
    require_all_contradictions_resolved: bool
    min_rounds_for_completion: int = 1

@dataclass
class SearchPolicy(PolicyBase):
    provider_priority: List[str]
    max_search_per_task: int
    dedupe_content: bool = True
    cooldown_seconds: int = 5

@dataclass
class CSIPolicy(PolicyBase):
    version: str
    mode: CSIMode
    workflow_type: WorkflowType
    mode_label: str
    claims: ClaimPolicy
    reviews: ReviewPolicy
    verdicts: VerdictPolicy
    provenance: ProvenancePolicy
    gates: GatePolicy
    search: SearchPolicy
    roles: Dict[str, RoleContract]
    prompts: Dict[str, str] = field(default_factory=dict)

def build_csi_policy(mode: str) -> CSIPolicy:
    """Factory to produce deterministic policies based on mode."""
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == CSIMode.HEALTH:
        return _build_health_policy()
    return _build_deepresearch_policy()

def _build_health_policy() -> CSIPolicy:
    return CSIPolicy(
        version="2.0.0",
        mode=CSIMode.HEALTH,
        workflow_type=WorkflowType.BLACKBOARD,
        mode_label="Evidence-Based Clinical Assessment",
        claims=ClaimPolicy(
            required_evidence_count=2,
            allow_unsupported=False,
            requires_cross_specialty_review=True,
            auto_validate_threshold=0.9
        ),
        reviews=ReviewPolicy(
            min_reviews_per_claim=2,
            require_opposing_role=True
        ),
        verdicts=VerdictPolicy(
            support_threshold=0.8,
            contradiction_threshold=0.2,
            auto_resolve_contradictions=False
        ),
        provenance=ProvenancePolicy(
            strict_domain_validation=True,
            allowed_domains=[
                "pubmed.ncbi.nlm.nih.gov", "who.int", "cdc.gov", "cochrane.org", 
                "fda.gov", "ema.europa.eu", "nice.org.uk", "thelancet.com", "nejm.org"
            ],
            tier_weights={"tier1": 1.0, "tier2": 0.7, "tier3": 0.3}
        ),
        gates=GatePolicy(
            max_rounds=10,
            max_no_progress_cycles=3,
            min_claims_for_synthesis=1,
            min_rounds_for_completion=2,
            require_all_contradictions_resolved=True
        ),
        search=SearchPolicy(
            provider_priority=["pubmed", "google_scholar", "bing_clinical"],
            max_search_per_task=1
        ),
        roles={
            "specialist": RoleContract(
                role_id="specialist",
                allowed_actions=["SEARCH_EVIDENCE", "PROPOSE_CLAIM", "REVIEW_CLAIM", "REVISE_CLAIM"],
                required_task_types=["PROPOSE_CLAIM", "REVIEW_CLAIM"],
                disallowed_task_types=["SYNTHESIZE_TOPIC"],
                evidence_obligations=2
            ),
            "lead_md": RoleContract(
                role_id="lead_md",
                allowed_actions=["REVIEW_CLAIM", "RESOLVE_CONTRADICTION", "SYNTHESIZE_TOPIC", "DRAFT_REPORT"],
                required_task_types=["SYNTHESIZE_TOPIC"],
                disallowed_task_types=["SEARCH_EVIDENCE"],
                evidence_obligations=1,
                synthesis_eligibility=True
            )
        }
    )

def _build_deepresearch_policy() -> CSIPolicy:
    return CSIPolicy(
        version="2.0.0",
        mode=CSIMode.DEEP_RESEARCH,
        workflow_type=WorkflowType.BLACKBOARD,
        mode_label="Deep Technical Research Swarm",
        claims=ClaimPolicy(
            required_evidence_count=1,
            allow_unsupported=True,
            requires_cross_specialty_review=False,
            auto_validate_threshold=0.8
        ),
        reviews=ReviewPolicy(
            min_reviews_per_claim=1,
            require_opposing_role=False
        ),
        verdicts=VerdictPolicy(
            support_threshold=0.7,
            contradiction_threshold=0.3,
            auto_resolve_contradictions=True
        ),
        provenance=ProvenancePolicy(
            strict_domain_validation=False,
            allowed_domains=[], # All allowed
            tier_weights={"tier1": 1.0, "tier2": 0.8, "tier3": 0.6}
        ),
        gates=GatePolicy(
            max_rounds=15,
            max_no_progress_cycles=5,
            min_claims_for_synthesis=3,
            min_rounds_for_completion=3,
            require_all_contradictions_resolved=False
        ),
        search=SearchPolicy(
            provider_priority=["bing", "google", "arxiv"],
            max_search_per_task=3
        ),
        roles={
            "researcher": RoleContract(
                role_id="researcher",
                allowed_actions=["SEARCH_EVIDENCE", "PROPOSE_CLAIM", "REVIEW_CLAIM", "REVISE_CLAIM", "SYNTHESIZE_TOPIC"],
                required_task_types=["SEARCH_EVIDENCE", "PROPOSE_CLAIM"],
                disallowed_task_types=[],
                evidence_obligations=1,
                synthesis_eligibility=True
            )
        }
    )
