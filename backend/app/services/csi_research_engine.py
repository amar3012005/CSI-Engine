"""
CSI Research Round Engine
~~~~~~~~~~~~~~~~~~~~~~~~~
Replaces template-based bootstrap in simulation_csi_local.py with real
LLM-powered investigation, proposal, peer-review, revision, and synthesis
rounds.
"""

from __future__ import annotations

import os
import re
import json
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..services.text_processor import TextProcessor
from .agent_harness import AgentHarness, ActionType, ActionResult

logger = get_logger("mirofish.csi_research_engine")

# ---------------------------------------------------------------------------
# Dataclass-like typed dicts for clarity
# ---------------------------------------------------------------------------

_VALID_VERDICTS = {"supports", "contradicts", "needs_revision"}


def _is_access_denied_llm_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "permissiondeniederror" in message
        or "access denied" in message
        or "check your network settings" in message
        or "error code: 403" in message
    )


def _safe_float(val: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(float(val), 1.0))
    except (TypeError, ValueError):
        return default


def _extract_field(text: str, label: str) -> str:
    """Pull a labelled section from LLM output.

    Handles formats like:
      CLAIM: some text
      **CLAIM:** some text
      **1. CLAIM** some text
      1. **CLAIM**: some text
      ## CLAIM\nsome text
    """
    esc = re.escape(label)
    # Try multiple patterns in order of specificity
    patterns = [
        # **N. LABEL** content ... (stops at next **N. or end)
        rf"(?:^|\n)\s*\**\s*\d+[\.\)]\s*\**\s*{esc}\s*\**[:\s]*(.+?)(?=\n\s*\**\s*\d+[\.\)]\s*\**\s*[A-Z]|$)",
        # **LABEL:** content or **LABEL** content
        rf"(?:^|\n)\s*\**\s*{esc}\s*\**\s*[:\-]?\s*(.+?)(?=\n\s*\**\s*(?:\d+[\.\)])?[A-Z_]+|$)",
        # LABEL: content (plain)
        rf"(?:^|\n)\s*{esc}\s*:\s*(.+?)(?=\n\s*[A-Z_]+\s*:|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            result = match.group(1).strip()
            # Remove leading markdown artifacts
            result = re.sub(r"^\*+\s*", "", result)
            if result:
                return result
    return ""


def _extract_confidence(text: str) -> float:
    """Extract confidence value from LLM output, handling various formats."""
    # First try the structured field
    raw = _extract_field(text, "CONFIDENCE")
    if raw:
        match = re.search(r"(\d+(?:\.\d+)?)", raw)
        if match:
            return _safe_float(match.group(1))
    # Fallback: look for "confidence" followed by a number anywhere
    match = re.search(r"confidence[:\s*]*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return _safe_float(match.group(1))
    return 0.5


def _dedupe_preserve_order(values: List[Any]) -> List[Any]:
    result: List[Any] = []
    seen: set[Any] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_source_url(url: str) -> str:
    if not url:
        return ""
    normalized = url.strip()
    normalized = re.sub(r"#.*$", "", normalized)
    normalized = normalized.rstrip("/")
    return normalized.lower()


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_propose_messages(
    agent: Dict[str, Any],
    source_snippets: str,
    simulation_requirement: str,
    search_feedback: Optional[str] = None,
    config_mode: str = 'web_research',
) -> List[Dict[str, str]]:
    agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
    research_role = agent.get("research_role") or agent.get("role") or "investigator"
    responsibility = agent.get("responsibility") or "investigate claims"
    evidence_priority = agent.get("evidence_priority") or "balanced"

    system_msg = (
        f"You are {agent_name}, a {research_role} and professional {agent.get('profession', 'expert')}. "
        f"Your bio: {agent.get('bio', 'Expert investigator')}.\n"
        f"Your responsibility: {responsibility}.\n"
        f"Your expertise skills: {', '.join(agent.get('skills', []))}.\n"
        f"Your evidence priority: {evidence_priority}."
    )
    user_msg = (
        "Based on these source materials, propose a specific, evidence-grounded "
        f'claim relevant to the research question: "{simulation_requirement}"\n\n'
        f"Available Sources:\n{source_snippets}\n\n"
    )
    if search_feedback:
        user_msg += f"【PREVIOUS SEARCH FEEDBACK】\n{search_feedback}\n\n"
        
    user_msg += (
        "If you have strong evidence, construct a factual claim. "
        "If you explicitly lack enough evidence to verify a claim, request a web search by returning JSON only.\n\n"
        "If you need a web search, respond with a JSON object. If you have a claim, respond with a JSON object.\n\n"
        "Action 1 (PROPOSE_CLAIM):\n"
        "Respond with a raw JSON object:\n"
        "{\n"
        '  "action": "propose_claim",\n'
        '  "claim": "Your specific finding (2-4 sentences, matching your profession\'s tone)",\n'
        '  "confidence": 0.95,\n'
        '  "evidence": "Which specific sources support this"\n'
        "}\n\n"
        "Action 2 (SEARCH_WEB):\n"
        "Respond with a raw JSON object:\n"
        "{\n"
        '  "action": "search_web",\n'
        '  "query": "your technical search query"\n'
        "}\n\n"
        "If you are a Fact Checker, Domain Expert, or Challenger, you MUST use Action 2 (SEARCH_WEB) to verify claims against the web before proposing a conclusion."
    )
    if config_mode == 'health':
        user_msg += (
            "\n\nCLINICAL CONSTRAINT: Support every claim with a specific peer-reviewed citation or "
            "established clinical guideline. Do not speculate. State evidence level: A (RCTs/meta-analyses), "
            "B (cohort/case-control studies), or C (expert opinion/case reports). "
            "Flag any patient safety concerns immediately."
        )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_search_query_messages(
    agent: Dict[str, Any], simulation_requirement: str, round_num: int,
    config_mode: str = 'web_research',
) -> List[Dict[str, str]]:
    """Build prompts for generating search queries."""
    agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
    role = agent.get("research_role") or agent.get("role") or "Expert"
    responsibility = agent.get("responsibility") or "research"
    bio = agent.get("bio", "Expert investigator")

    system_msg = (
        f"You are {agent_name}, a {role}.\n"
        f"Bio: {bio}\n"
        f"Your responsibility: {responsibility}\n"
        "Generate focused search queries to gather evidence."
    )
    effective_requirement = simulation_requirement
    if config_mode == 'health':
        effective_requirement = f"clinical evidence {simulation_requirement}"
    user_msg = (
        f"Task: Generate 2-3 specific search queries to investigate: \"{effective_requirement}\"\n\n"
        "Respond with ONLY a JSON object:\n"
        "{\n"
        '  "search_queries": ["query 1", "query 2"]\n'
        "}"
    )
    if config_mode == 'health':
        user_msg += (
            "\n\nPrefer sources from: PubMed, Cochrane Library, WHO guidelines, "
            "and clinical practice guidelines when generating queries."
        )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_synthesis_messages(
    agent: Dict[str, Any], claims_text: str, simulation_requirement: str,
    config_mode: str = 'web_research',
) -> List[Dict[str, str]]:
    """Build prompts for claim synthesis."""
    agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
    role = agent.get("research_role") or agent.get("role") or "Expert"

    system_msg = (
        f"You are {agent_name}, a {role}.\n"
        "Synthesize these related claims into a consolidated finding."
    )
    if config_mode == 'health':
        user_msg = (
            f"Consolidate these claims for: \"{simulation_requirement}\"\n\n"
            f"Claims:\n{claims_text}\n\n"
            "OUTPUT FORMAT for Health Mode (return as JSON):\n"
            "{\n"
            '  "case_summary": "Brief patient case overview",\n'
            '  "differential_diagnoses": [\n'
            '    {"rank": 1, "diagnosis": "...", "confidence": 0.85, "evidence_level": "A", "reasoning": "..."},\n'
            "    ...\n"
            "  ],\n"
            '  "clinical_reasoning": "Narrative explanation of diagnostic process",\n'
            '  "recommended_investigations": ["CBC", "CT scan", "..."],\n'
            '  "management_plan": ["Step 1: ...", "Step 2: ..."],\n'
            '  "safety_alerts": ["Drug X contraindicated with Drug Y", "..."],\n'
            '  "references": ["Guideline/study citations..."]\n'
            "}"
        )
    else:
        user_msg = (
            f"Consolidate these claims for: \"{simulation_requirement}\"\n\n"
            f"Claims:\n{claims_text}\n\n"
            "Respond with:\n"
            "CLAIM: [Your synthesized finding]\n"
            "CONFIDENCE: [0.0-1.0]\n"
            "EVIDENCE: [Key supporting points]"
        )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_review_messages(
    reviewer: Dict[str, Any],
    proposer: Dict[str, Any],
    claim_text: str,
    source_snippets: str,
    search_feedback: Optional[str] = None,
    config_mode: str = 'web_research',
) -> List[Dict[str, str]]:
    reviewer_name = reviewer.get("agent_name") or reviewer.get("entity_name") or "Reviewer"
    reviewer_role = reviewer.get("research_role") or reviewer.get("role") or "reviewer"
    reviewer_resp = reviewer.get("responsibility") or "review claims"
    proposer_name = proposer.get("agent_name") or proposer.get("entity_name") or "Proposer"
    proposer_role = proposer.get("research_role") or proposer.get("role") or "proposer"

    system_msg = (
        f"You are {reviewer_name}, a {reviewer_role} and {reviewer.get('profession', 'expert')}.\n"
        f"Your bio: {reviewer.get('bio', 'Expert reviewer')}.\n"
        f"You are adversarial and rigorous. You are reviewing a claim by {proposer_name} ({proposer_role}).\n"
        f"Use your specialized skills: {', '.join(reviewer.get('skills', []))} to CHALLENGE this claim."
    )
    user_msg = (
        "Review this claim against available evidence. If it is weak from a [Profession] standpoint, CHALLENGE IT.\n\n"
        f"CLAIM: {claim_text}\n"
        f"SOURCES CITED: {source_snippets}\n\n"
    )
    if search_feedback:
        user_msg += f"【PREVIOUS SEARCH FEEDBACK】\n{search_feedback}\n\n"
        
    user_msg += (
        "Respond with ONLY a raw JSON object choosing ONE of these two actions:\n\n"
        "If you decide to SEARCH to verify, respond with a raw JSON object containing action='search_web' and query.\n"
        "If you have a review verdict, respond with JSON.\n\n"
        "Action 1 (CHALLENGE_CLAIM / VERIFY):\n"
        "Respond with a raw JSON object:\n"
        "{\n"
        '  "action": "peer_review",\n'
        '  "verdict": "supports" OR "contradicts" OR "needs_revision",\n'
        '  "reasoning": "Scientific/Profession-driven reasoning (2-3 sentences)",\n'
        '  "critique": "Specific flaws or missing context identified"\n'
        "}\n\n"
        "Action 2 (SEARCH_WEB):\n"
        "Respond with a raw JSON object:\n"
        "{\n"
        '  "action": "search_web",\n'
        '  "query": "specific query keyword phrase"\n'
        "}\n\n"
        "If you are reviewing a claim from a contradictory role (e.g. Challenger reviewing Expert), you SHOULD use Action 2 to find real-world evidence for your critique."
    )
    if config_mode == 'health':
        user_msg += (
            "\n\nCLINICAL REVIEW CONSTRAINT: Flag any claim that: "
            "(1) contradicts established clinical guidelines, "
            "(2) lacks evidence-based support, "
            "(3) poses patient safety risk such as dangerous drug interactions or contraindications, "
            "(4) overlooks critical patient-specific factors. "
            "Cite the guideline or evidence when flagging."
        )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_revise_messages(
    agent: Dict[str, Any],
    reviewer: Dict[str, Any],
    original_text: str,
    verdict: str,
    peer_reasoning: str,
    source_snippets: str,
) -> List[Dict[str, str]]:
    agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
    reviewer_name = reviewer.get("agent_name") or reviewer.get("entity_name") or "Reviewer"

    system_msg = (
        f"You are {agent_name}. Your peer {reviewer_name} has reviewed your claim."
    )
    user_msg = (
        "Revise your claim incorporating the peer feedback:\n\n"
        f"ORIGINAL CLAIM: {original_text}\n"
        f"PEER VERDICT: {verdict}\n"
        f"PEER REASONING: {peer_reasoning}\n"
        f"SOURCES: {source_snippets}\n\n"
        "Respond with your revised claim (2-4 sentences)."
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
# ---------------------------------------------------------------------------
# Source formatting helpers
# ---------------------------------------------------------------------------

def _format_source_snippets(sources: List[Dict[str, Any]], max_chars: int = 3000) -> str:
    """Flatten selected sources into a prompt-friendly text block with intelligent chunking."""
    parts: List[str] = []
    budget = max_chars

    for idx, src in enumerate(sources, 1):
        title = src.get("title") or f"Source {idx}"
        full_content = src.get("summary") or src.get("content") or ""

        # Intelligent chunking: extract first meaningful paragraph or 150 words
        if full_content:
            # Split into sentences/paragraphs
            paragraphs = [p.strip() for p in full_content.split('\n\n') if p.strip()]
            if paragraphs:
                # Take first paragraph, limited to 200 words
                first_para = paragraphs[0][:800]  # ~150-200 words
                # Ensure it ends at sentence boundary
                if '.' in first_para[-100:]:
                    last_period = first_para.rfind('.')
                    if last_period > len(first_para) * 0.7:  # Don't cut too early
                        first_para = first_para[:last_period + 1]
                content = first_para
            else:
                # Fallback: first 400 chars
                content = full_content[:400]
        else:
            content = "No content available"

        entry = f"[{idx}] {title}: {content}"
        if len(entry) > budget:
            entry = entry[:budget]
            # Ensure it doesn't cut mid-word
            if ' ' in entry[-50:]:
                last_space = entry.rfind(' ')
                if last_space > budget * 0.8:
                    entry = entry[:last_space]

        parts.append(entry)
        budget -= len(entry)
        if budget <= 0:
            break

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CSIResearchEngine:
    """Runs LLM-powered CSI research rounds: investigate, propose, review,
    revise, and synthesize claims using an existing LLMClient and CSI store."""

    def __init__(
        self,
        simulation_id: str,
        harness: AgentHarness,
        csi_store: Any,  # SimulationCSILocalStore
        sources: List[Dict[str, Any]],
        roster: List[Dict[str, Any]],
        config: Any,  # ResearchWorkflowConfig
        quality_config: Dict[str, Any] | None = None,
        config_mode: str = 'web_research',
    ) -> None:
        self.simulation_id = simulation_id
        self.harness = harness
        self.llm = harness.llm
        self.store = csi_store
        self.sources = sources
        self.roster = roster
        self.config = config
        self.config_mode = config_mode
        self.quality_config = quality_config or {
            "min_content_length": 50,
            "min_title_length": 3,
            "min_search_score": 0.1,
            "require_news_indicators": False,
            "strict_domain_filter": False,
            "max_ad_indicators": 5,
            "english_only": True,
        }

        # Unpack policy dicts with sane defaults.
        # config may be a dict (from JSON) or a dataclass — handle both.
        def _cfg(key: str) -> Dict[str, Any]:
            if isinstance(config, dict):
                return config.get(key) or {}
            return getattr(config, key, None) or {}

        claim_policy = _cfg("claim_policy")
        debate_policy = _cfg("debate_policy")
        verdict_policy = _cfg("verdict_policy")
        gate_policy = _cfg("gate_policy")

        self._min_claims_per_agent: int = int(claim_policy.get("min_claims_per_agent", 1))
        self._require_opposing_review: bool = bool(debate_policy.get("require_opposing_review", True))
        self._max_unreviewed_ratio: float = float(debate_policy.get("max_unreviewed_claim_ratio", 0.15))
        self._require_evidence_count: int = int(verdict_policy.get("require_evidence_count", 1))
        self._min_source_coverage: int = int(gate_policy.get("minimum_source_coverage", 3))
        self._min_reviewed_ratio: float = float(gate_policy.get("minimum_reviewed_claim_ratio", 0.8))
        self._block_on_missing_provenance: bool = bool(gate_policy.get("block_on_missing_provenance", True))

        # Lazy web search client (optional — only created if TAVILY_API_KEY is set)
        self._web_search_client: Any = None
        self._web_search_checked: bool = False

        # Bookkeeping
        self._claims: List[Dict[str, Any]] = []
        self._trials: List[Dict[str, Any]] = []
        self._unpublished_findings: List[Dict[str, Any]] = [] # For findings before finalized claims
        self._unique_sources_cited: set[str] = set()

        # Concurrency locks for shared state mutations
        self._claims_lock = threading.Lock()
        self._trials_lock = threading.Lock()
        self._sources_lock = threading.Lock()

        # Groq Native Tool Client for 'Native Intelligence' turns
        self.groq_native = None
        if "groq" in Config.LLM_MODEL_NAME.lower() or "compound" in Config.LLM_MODEL_NAME.lower():
            try:
                from ..utils.groq_native_client import GroqNativeClient
                self.groq_native = GroqNativeClient()
            except Exception as e:
                logger.warning(f"Failed to initialize GroqNativeClient: {e}")

    def _load_simulation_config(self) -> Dict[str, Any]:
        try:
            sim_dir = self.store._sim_dir(self.simulation_id)
            config_path = os.path.join(sim_dir, "simulation_config.json")
            if not os.path.exists(config_path):
                return {}
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Failed to load simulation config for continuation context: %s", exc)
            return {}

    def _build_continuation_requirement(self, simulation_requirement: str) -> str:
        config = self._load_simulation_config()
        checkpoints = config.get("checkpoints") or []
        if not checkpoints:
            return simulation_requirement

        last_checkpoint = checkpoints[-1]
        summary = last_checkpoint.get("artifact_summary") or {}
        previous_query = last_checkpoint.get("query") or "previous research goal"
        return (
            "PRIOR RESEARCH CONTEXT:\n"
            "You are continuing research in an active sandbox.\n"
            f"Previous goal: \"{previous_query}\"\n"
            f"Current goal: \"{simulation_requirement}\"\n\n"
            "Existing artifacts available to you:\n"
            f"- {int(summary.get('claims', 0) or 0)} claims (use RECALL before proposing new ones)\n"
            f"- {int(summary.get('sources', 0) or 0)} sources (reuse before searching for new ones)\n"
            f"- {int(summary.get('trials', 0) or 0)} trials (prior verification results remain available)\n\n"
            "RULES FOR CONTINUATION:\n"
            "1. RECALL existing claims and sources FIRST before any SEARCH_WEB\n"
            "2. Reuse relevant prior artifacts instead of duplicating them\n"
            "3. Only SEARCH_WEB when existing evidence is insufficient for the new goal\n"
            "4. New claims should extend prior findings unless new evidence contradicts them\n\n"
            f"ACTIVE RESEARCH QUESTION: {simulation_requirement}"
        )

    def _refresh_round_blackboard(self) -> Dict[str, Any]:
        blackboard_state: Dict[str, Any] = {}
        with self._sources_lock:
            self.sources = self.store._load_sources_index(self.simulation_id).get("sources", [])
        if hasattr(self.store, "refresh_blackboard_state"):
            try:
                blackboard_state = self.store.refresh_blackboard_state(self.simulation_id) or {}
            except Exception as exc:
                logger.warning("Failed to refresh round blackboard for %s: %s", self.simulation_id, exc)
        return {
            "source_count": len(self.sources),
            "claim_count": len(self._claims),
            "trial_count": len(self._trials),
            "blackboard": blackboard_state.get("blackboard") or {},
        }

    def _load_blackboard_recall_context(self) -> Dict[str, Any]:
        blackboard_state = {}
        if hasattr(self.store, "_load_state"):
            try:
                blackboard_state = self.store._load_state(self.simulation_id).get("blackboard") or {}
            except Exception as exc:
                logger.warning("Failed to load CSI blackboard state for recall: %s", exc)

        supported_source_ids: set[str] = set()
        contradicted_source_ids: set[str] = set()
        try:
            claims = self.store._read_jsonl(self.store._path(self.simulation_id, "claims.jsonl"))
            trials = self.store._read_jsonl(self.store._path(self.simulation_id, "trials.jsonl"))
            claim_sources = {
                str(claim.get("claim_id")): [source_id for source_id in (claim.get("source_ids") or []) if source_id]
                for claim in claims
                if claim.get("claim_id")
            }
            for trial in trials:
                claim_id = str(trial.get("claim_id") or "")
                source_ids = claim_sources.get(claim_id, [])
                verdict = str(trial.get("verdict") or "").lower()
                if verdict == "supports":
                    supported_source_ids.update(source_ids)
                elif verdict == "contradicts":
                    contradicted_source_ids.update(source_ids)
        except Exception as exc:
            logger.warning("Failed to build blackboard recall context: %s", exc)

        return {
            "reviewed_claim_ids": set(blackboard_state.get("reviewed_claim_ids") or []),
            "unique_source_ids": set(blackboard_state.get("unique_source_ids") or []),
            "supported_source_ids": supported_source_ids,
            "contradicted_source_ids": contradicted_source_ids,
        }

    def _run_agent_round_turn(
        self,
        round_num: int,
        agent: Dict[str, Any],
        simulation_requirement: str,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        recall = self._run_investigation_phase(round_num, agent, simulation_requirement)
        selected_sources = recall.get("selected_sources", [])
        if not selected_sources:
            return [], False

        produced_claims: List[Dict[str, Any]] = []
        refresh_requested = False
        claims_needed = max(self._min_claims_per_agent, 1)
        for _ in range(claims_needed):
            claim = self._run_proposal_phase(round_num, agent, recall, simulation_requirement)
            if isinstance(claim, dict) and claim.get("type") == "search_result":
                refresh_requested = True
                break
            if isinstance(claim, dict) and claim.get("type") == "redirect_to_recall":
                break
            if isinstance(claim, dict) and "claim_id" in claim:
                produced_claims.append(claim)
        return produced_claims, refresh_requested

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_research_rounds(
        self,
        num_rounds: int = 3,
        simulation_requirement: str = "",
        on_round_complete: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Main entry point. Runs investigation -> proposal -> peer review ->
        revision rounds, then an optional synthesis phase.

        Args:
            num_rounds: Number of research rounds to execute.
            simulation_requirement: The research question / requirement text.
            on_round_complete: Optional callback ``(round_index: int) -> None``
                invoked after each round finishes (0-based index).
        """
        logger.info(
            "Starting CSI research rounds",
            extra={
                "simulation_id": self.simulation_id,
                "num_rounds": num_rounds,
                "roster_size": len(self.roster),
                "source_count": len(self.sources),
            },
        )

        effective_requirement = self._build_continuation_requirement(simulation_requirement)

        # Track search_web intents per agent per round to prevent infinite loops
        _search_web_budget: Dict[str, int] = {}  # agent_id -> remaining searches this round
        MAX_SEARCHES_PER_AGENT_PER_ROUND = 1
        MAX_PASSES_PER_ROUND = 3
        # Thread pool for parallel agent execution
        MAX_PARALLEL_AGENTS = min(len(self.roster), 8)

        for round_num in range(1, num_rounds + 1):
            logger.info("Round %d/%d", round_num, num_rounds)
            round_claims: List[Dict[str, Any]] = []
            round_claims_lock = threading.Lock()
            round_search_refresh_requested = False

            if hasattr(self.store, "advance_round_count"):
                try:
                    self.store.advance_round_count(self.simulation_id, round_num, source="research_round")
                except Exception as exc:
                    logger.warning("Failed to advance round count at round %d start: %s", round_num, exc)

            self._refresh_round_blackboard()

            # Reset search budget per round
            for agent in self.roster:
                _search_web_budget[str(agent.get("agent_id"))] = MAX_SEARCHES_PER_AGENT_PER_ROUND

            # ---------------------------------------------------------
            # SWARM PHASE 1: INVESTIGATION (Parallel)
            # ---------------------------------------------------------
            logger.info("Swarm Phase 1: Collective Investigation")
            
            def _individual_investigation(agent: Dict[str, Any]) -> None:
                agent_id = str(agent.get("agent_id"))
                recall = self._run_investigation_phase(round_num, agent, effective_requirement)

                if not self._agent_has_action(agent, "SEARCH_WEB"):
                    return

                local_evidence_count = len(recall.get("selected_sources", []))
                role = (agent.get("role") or "unknown").lower()

                # MANDATORY DEFERRAL: In Round 1, agents MUST prioritize swarm coordination over web search
                # unless they have NO evidence.
                needs_search = False
                if local_evidence_count == 0:
                    # Absolute gap — search allowed even in R1
                    needs_search = True
                elif round_num >= 2:
                    # From R2 onwards, specific roles or low evidence trigger search
                    if local_evidence_count < 3:
                        needs_search = True
                    elif role in ["explorer", "fact_checker", "challenger"]:
                        needs_search = True

                if needs_search and _search_web_budget.get(agent_id, 0) > 0:
                    queries = self._generate_search_queries(agent, effective_requirement, round_num)
                    query = queries[0] if queries else None
                    if query:
                        _search_web_budget[agent_id] -= 1
                        web_client = self._get_web_client()
                        if web_client:
                            logger.info("Search Wave: [%s] searching for: '%s' (Round %d)", agent.get("agent_name"), query, round_num)
                            # Primary: Groq Compound (Native reasoning search)
                            csi_sources = web_client.search_as_csi_sources(
                                query=query,
                                agent_name=agent.get("agent_name"),
                                round_num=round_num,
                                max_results=3,
                                search_depth="basic",
                                provider_mode="groq_only"
                            )
                            # Fallback: Tavily (Direct web search) if Groq returns nothing
                            if not csi_sources and web_client.is_tavily_available():
                                logger.info("Groq search yielded 0 results; falling back to Tavily for query: '%s'", query)
                                csi_sources = web_client.search_as_csi_sources(
                                    query=query,
                                    agent_name=agent.get("agent_name"),
                                    round_num=round_num,
                                    max_results=3,
                                    search_depth="advanced",
                                    provider_mode="tavily_only"
                                )
                            self._ingest_web_results(
                                self.simulation_id,
                                csi_sources,
                                agent,
                                round_num,
                                search_query=query,
                                discovery_kind="agent_search",
                            )

            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as executor:
                futures = [executor.submit(_individual_investigation, agent) for agent in self.roster]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        logger.warning("Agent investigation failed: %s", exc)

            # Refresh blackboard after all investigators publish findings
            self._refresh_round_blackboard()
            
            # Check gate policy after investigation phase
            if self._check_gate_policy():
                logger.info("Gate policy satisfied after collective investigation — stopping early")
                break

            def _review_claim(claim: Dict[str, Any]) -> None:
                proposer = self._find_agent(claim.get("agent_id"))
                if not proposer:
                    return

                # Select TWO diverse reviewers per claim to cut token costs by 70% while maintaining adversarial quality
                selected_reviewer_ids: set[str] = set()
                for _ in range(2):
                    reviewer = self._pick_reviewer(proposer, claim, exclude_agent_ids=selected_reviewer_ids)
                    if not reviewer:
                        break
                    
                    selected_reviewer_ids.add(reviewer.get("agent_id"))
                    
                    trial = self._run_peer_review_phase(
                        round_num, claim, proposer, reviewer, effective_requirement
                    )

                    if isinstance(trial, dict) and trial.get("type") == "search_result":
                        reviewer_id = str(reviewer.get("agent_id"))
                        if _search_web_budget.get(reviewer_id, 0) > 0:
                            _search_web_budget[reviewer_id] -= 1
                            nonlocal round_search_refresh_requested
                            round_search_refresh_requested = True
                            search_feedback = None
                            if trial.get("ingested_count", 0) == 0:
                                search_feedback = f"Your previous web search for '{trial.get('query')}' yielded 0 new useful sources. You must render a verdict based on existing evidence."
                            trial = self._run_peer_review_phase(
                                round_num, claim, proposer, reviewer, effective_requirement, search_feedback=search_feedback
                            )

                    # --- Phase 4: revision if needed ----
                    if isinstance(trial, dict) and trial.get("verdict") == "needs_revision":
                        self._run_revision_phase(
                            round_num, proposer, claim, trial, effective_requirement
                        )

            for pass_index in range(MAX_PASSES_PER_ROUND):
                if pass_index > 0:
                    self._refresh_round_blackboard()

                pass_claims: List[Dict[str, Any]] = []
                pass_claims_lock = threading.Lock()
                pass_refresh_requested = False

                def _investigate_and_propose(agent: Dict[str, Any]) -> None:
                    nonlocal pass_refresh_requested
                    existing_claims = sum(1 for claim in round_claims if claim.get("agent_id") == agent.get("agent_id"))
                    if existing_claims >= max(self._min_claims_per_agent, 1):
                        return

                    agent_id = str(agent.get("agent_id"))
                    # RECALL refreshed context before proposal
                    recall = self._run_investigation_phase(round_num, agent, effective_requirement)
                    
                    # PROPOSE
                    claim = self._run_proposal_phase(round_num, agent, recall, effective_requirement)
                    
                    if isinstance(claim, dict):
                        if claim.get("type") == "search_result":
                            if _search_web_budget.get(agent_id, 0) > 0:
                                _search_web_budget[agent_id] -= 1
                                pass_refresh_requested = True
                            return
                        if claim.get("type") == "redirect_to_recall":
                            return
                        if "claim_id" in claim:
                            with pass_claims_lock:
                                pass_claims.append(claim)

                with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as executor:
                    futures = {executor.submit(_investigate_and_propose, agent): agent for agent in self.roster}
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as exc:
                            agent = futures[future]
                            logger.warning(
                                "Agent %s failed in investigate/propose phase: %s",
                                agent.get("agent_name"), exc
                            )

                if pass_claims:
                    with round_claims_lock:
                        round_claims.extend(pass_claims)

                    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as executor:
                        futures = {executor.submit(_review_claim, claim): claim for claim in pass_claims}
                        for future in as_completed(futures):
                            try:
                                future.result()
                            except Exception as exc:
                                logger.warning("Peer review failed for a claim: %s", exc)

                round_search_refresh_requested = round_search_refresh_requested or pass_refresh_requested
                if not pass_claims and not pass_refresh_requested:
                    break

            # --- Phase 5: synthesis (last round only) ----
            if round_num == num_rounds and len(self._claims) > 1:
                def _synthesize_agent(agent: Dict[str, Any]) -> None:
                    reviewed_ids = {t.get("claim_id") for t in self._trials}
                    agent_claims = [
                        c for c in self._claims
                        if c.get("agent_id") == agent.get("agent_id")
                        and c.get("claim_id") in reviewed_ids
                        and self._is_valid_claim_text(c.get("text", ""))
                    ]
                    if len(agent_claims) >= 2:
                        self._run_synthesis_phase(
                            round_num, agent, agent_claims, effective_requirement
                        )

                with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as executor:
                    futures = [executor.submit(_synthesize_agent, agent) for agent in self.roster]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as exc:
                            logger.warning("Synthesis failed for an agent: %s", exc)

            if hasattr(self.store, "refresh_blackboard_state"):
                try:
                    self.store.refresh_blackboard_state(self.simulation_id)
                except Exception as exc:
                    logger.warning("Failed to refresh CSI blackboard after round %d: %s", round_num, exc)

            # Notify caller of round completion after persisted state is current.
            if on_round_complete is not None:
                try:
                    on_round_complete(round_num - 1)
                except Exception as cb_exc:
                    logger.warning(
                        "on_round_complete callback failed: %s", cb_exc
                    )

            # Gate check after each round
            if self._check_gate_policy():
                logger.info(
                    "Gate policy satisfied after round %d — stopping early",
                    round_num,
                )
                break

        if hasattr(self.store, "refresh_blackboard_state"):
            try:
                self.store.refresh_blackboard_state(self.simulation_id)
            except Exception as exc:
                logger.warning("Failed to refresh CSI blackboard at run end: %s", exc)

        web_source_count = sum(
            1 for s in self.sources if s.get("source_type") == "web"
        )
        summary = {
            "rounds_completed": round_num,
            "total_claims": len(self._claims),
            "total_trials": len(self._trials),
            "unique_sources_cited": len(self._unique_sources_cited),
            "web_sources_discovered": web_source_count,
            "reviewed_ratio": self._reviewed_ratio(),
        }

        # Phase 4: State Preservation — save reusable blueprint
        self._save_blueprint(simulation_requirement)

        logger.info("Research rounds complete: %s", summary)
        return summary

    def collect_sources(
        self,
        simulation_requirement: str,
        round_num: int = 1,
        on_progress: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Collect sources only (web search + optional deep-read) without
        generating claims/trials. Intended for pre-run source collection."""
        discovered_total = 0
        deep_read_total = 0
        agents_with_search = 0

        for idx, agent in enumerate(self.roster, start=1):
            agent_name = agent.get("agent_name") or agent.get("entity_name") or f"Agent {idx}"
            if on_progress:
                try:
                    on_progress(idx, len(self.roster), agent_name)
                except Exception:
                    pass

            # Step 2 should stay source-first: one query, one pass, no reflection loop.
            discovered: List[Dict[str, Any]] = []
            if self._agent_has_action(agent, "SEARCH_WEB"):
                web_client = self._get_web_client()
                if web_client is not None:
                    queries = self._generate_search_queries(agent, simulation_requirement, round_num)
                    query = queries[0] if queries else simulation_requirement[:120]
                    if query:
                        csi_sources = web_client.search_as_csi_sources(
                            query=query,
                            agent_name=agent_name,
                            round_num=round_num,
                            max_results=5,
                            search_depth="basic",
                            provider_mode="groq_only",
                        )
                        discovered = self._ingest_web_results(
                            self.simulation_id,
                            csi_sources,
                            agent,
                            round_num,
                            search_query=query,
                            discovery_kind="agent_search",
                        )

                        self.store.record_agent_action(self.simulation_id, {
                            "action_type": "SEARCH_WEB",
                            "agent_id": agent.get("agent_id"),
                            "agent_name": agent_name,
                            "entity_uuid": agent.get("entity_uuid"),
                            "entity_name": agent.get("entity_name"),
                            "entity_type": agent.get("entity_type"),
                            "role": agent.get("role"),
                            "round_num": round_num,
                            "detail": {
                                "query": query,
                                "results_count": len(csi_sources),
                                "ingested_count": len(discovered),
                                "urls": [r.get("url", "") for r in csi_sources],
                                "phase": "source_collection",
                            },
                        })

                        logger.info(
                            "Source collection SEARCH_WEB: agent=%s query='%s' found=%d ingested=%d",
                            agent_name, query, len(csi_sources), len(discovered)
                        )

            if discovered:
                discovered_total += len(discovered)
                agents_with_search += 1

                if self._agent_has_action(agent, "READ_URL"):
                    urls_to_read = self._select_urls_for_deep_read(
                        agent, discovered, simulation_requirement
                    )
                    if urls_to_read:
                        deep_sources = self._run_deep_read_phase(
                            round_num, agent, urls_to_read
                        )
                        deep_read_total += len(deep_sources or [])

        # Advance round count in CSI store if available.
        if hasattr(self.store, "advance_round_count"):
            try:
                self.store.advance_round_count(self.simulation_id, round_num, source="collect_sources")
            except Exception:
                pass

        web_source_count = sum(
            1 for s in self.sources if s.get("source_type") == "web"
        )

        return {
            "round_num": round_num,
            "agents_with_search": agents_with_search,
            "sources_discovered": discovered_total,
            "sources_deep_read": deep_read_total,
            "web_sources_total": web_source_count,
        }

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _run_investigation_phase(
        self,
        round_num: int,
        agent: Dict[str, Any],
        simulation_requirement: str,
    ) -> Dict[str, Any]:
        """Agent investigates sources relevant to their goal. Returns recall
        dict with selected_sources and snippets."""
        query_terms = self._agent_query_terms(agent, simulation_requirement)
        blackboard_context = self._load_blackboard_recall_context()
        # Restore standard recall limit for Agent prompts to save tokens
        selected = self._select_sources(self.sources, query_terms, limit=4, blackboard_context=blackboard_context)

        source_ids = [s.get("source_id") for s in selected]
        snippets = [
            {
                "source_id": s.get("source_id"),
                "title": s.get("title"),
                "snippet": (s.get("summary") or s.get("content", ""))[:240],
            }
            for s in selected
        ]

        recall_record = self.store.record_recall(self.simulation_id, {
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "query": " ".join(query_terms[:20]),
            "source_ids": source_ids,
            "snippets": snippets,
            "score": round(sum(s.get("priority", 0.0) for s in selected), 3),
            "round_num": round_num,
        })

        self.store.record_agent_action(self.simulation_id, {
            "action_type": "investigate_source",
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "round_num": round_num,
            "detail": {
                "recall_id": recall_record.get("recall_id"),
                "source_count": len(selected),
            },
        })

        return {
            "recall_record": recall_record,
            "selected_sources": selected,
            "snippets": snippets,
            "source_ids": source_ids,
        }

    def _run_proposal_phase(
        self,
        round_num: int,
        agent: Dict[str, Any],
        recall: Dict[str, Any],
        simulation_requirement: str,
        search_feedback: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Agent proposes a claim via AgentHarness."""
        selected_sources = recall.get("selected_sources", [])
        source_snippets = _format_source_snippets(selected_sources, max_chars=1000)
        source_ids = _dedupe_preserve_order([s.get("source_id") for s in selected_sources])

        messages = _build_propose_messages(agent, source_snippets, simulation_requirement, search_feedback=search_feedback, config_mode=self.config_mode)

        # Execute through the single harness execution layer
        result: ActionResult = self.harness.execute(
            action_type=ActionType.PROPOSE_CLAIM,
            agent=agent,
            payload={"messages": messages},
            round_num=round_num
        )

        if result.is_search:
            search_results = result.search_results
            if not search_results and result.search_query:
                search_results = self._execute_search_query(agent, result.search_query, round_num)

            # Re-ingest and signal refresh
            ingested = self._ingest_web_results(
                self.simulation_id,
                search_results,
                agent,
                round_num,
                search_query=result.search_query,
                discovery_kind="deferred_search",
            )
            with self._sources_lock:
                updated_idx = self.store._load_sources_index(self.simulation_id)
                self.sources = updated_idx.get("sources", [])
            
            return {
                "type": "search_result", 
                "ingested_count": len(ingested), 
                "query": result.search_query, 
                "requires_refresh": True
            }

        if not result.success:
            logger.warning("AgentHarness PROPOSE_CLAIM failed for %s", agent.get("agent_name"))
            return None

        # Process standard claim result
        claim_text = self._normalize_claim_text(result.data.get("claim", ""))
        if not self._is_valid_claim_text(claim_text):
            return None

        confidence = result.data.get("confidence", 0.5)
        
        claim_record = self.store.record_claim(self.simulation_id, {
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "text": claim_text,
            "source_ids": source_ids,
            "confidence": confidence,
            "status": "proposed",
            "round_num": round_num,
        })

        # Record action in store
        self.store.record_agent_action(self.simulation_id, {
            "action_type": "propose_claim",
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "round_num": round_num,
            "detail": {
                "claim_id": claim_record.get("claim_id"),
                "confidence": confidence,
                "source_count": len(source_ids),
                "harness_id": result.trace_id
            },
        })

        # Provenance: claim derived_from each source
        for sid in source_ids:
            self.store.record_relation(self.simulation_id, {
                "relation_type": "derived_from",
                "from_id": claim_record.get("claim_id"),
                "to_id": sid,
            })

        with self._claims_lock:
            self._claims.append(claim_record)
            self._unique_sources_cited.update(s for s in source_ids if s)
        return claim_record

    def _run_peer_review_phase(
        self,
        round_num: int,
        claim: Dict[str, Any],
        proposer: Dict[str, Any],
        reviewer: Dict[str, Any],
        simulation_requirement: str,
        search_feedback: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Peer reviews a claim via AgentHarness."""
        if not self._is_valid_claim_text(claim.get("text", "")):
            logger.warning("Skipping peer review for malformed claim %s", claim.get("claim_id"))
            return None

        # Re-select sources from reviewer's perspective
        query_terms = self._agent_query_terms(reviewer, claim.get("text", ""))
        selected_sources = self._select_sources(
            self.sources,
            query_terms,
            limit=3,
            blackboard_context=self._load_blackboard_recall_context(),
        )
        # Use reduced context for peer reviews to save tokens
        source_snippets = _format_source_snippets(selected_sources, max_chars=800)

        messages = _build_review_messages(
            reviewer, proposer, claim.get("text", ""), source_snippets, search_feedback=search_feedback,
            config_mode=self.config_mode,
        )

        # Execute through the harness
        result: ActionResult = self.harness.execute(
            action_type=ActionType.CHALLENGE_CLAIM,
            agent=reviewer,
            payload={"messages": messages, "context": {"target_claim_id": claim.get("claim_id")}},
            round_num=round_num
        )

        if result.is_search:
            search_results = result.search_results
            if not search_results and result.search_query:
                search_results = self._execute_search_query(reviewer, result.search_query, round_num)

            # Re-ingest and signal refresh
            ingested = self._ingest_web_results(
                self.simulation_id,
                search_results,
                reviewer,
                round_num,
                search_query=result.search_query,
                discovery_kind="deferred_search",
            )
            with self._sources_lock:
                updated_idx = self.store._load_sources_index(self.simulation_id)
                self.sources = updated_idx.get("sources", [])
            
            return {
                "type": "search_result", 
                "ingested_count": len(ingested), 
                "query": result.search_query, 
                "requires_refresh": True
            }

        if not result.success:
            logger.warning("AgentHarness PEER_REVIEW failed for %s", reviewer.get("agent_name"))
            return None

        verdict = result.data.get("verdict", "needs_revision").lower()
        if verdict not in _VALID_VERDICTS:
            verdict = "needs_revision"

        confidence = result.data.get("confidence", 0.5)
        critique = result.data.get("critique", result.data.get("reasoning", ""))

        review_record = self.store.record_review(self.simulation_id, {
            "claim_id": claim.get("claim_id"),
            "agent_id": reviewer.get("agent_id"),
            "agent_name": reviewer.get("agent_name"),
            "entity_uuid": reviewer.get("entity_uuid"),
            "entity_name": reviewer.get("entity_name"),
            "entity_type": reviewer.get("entity_type"),
            "role": reviewer.get("role"),
            "verdict": verdict,
            "text": critique,
            "confidence": confidence,
            "round_num": round_num,
        })

        trial_record = self.store.record_trial(self.simulation_id, {
            "trial_kind": "peer_review",
            "round_num": round_num,
            "query_agent_id": proposer.get("agent_id"),
            "query_agent_name": proposer.get("agent_name"),
            "target_agent_id": reviewer.get("agent_id"),
            "target_agent_name": reviewer.get("agent_name"),
            "claim_id": claim.get("claim_id"),
            "query": f"Review claim: {claim.get('text', '')[:200]}",
            "response": critique,
            "verdict": verdict,
            "source_ids": claim.get("source_ids") or [],
        })

        with self._trials_lock:
            self._trials.append(trial_record)

        relation_type = "supports" if verdict == "supports" else "contradicts"
        self.store.record_relation(self.simulation_id, {
            "relation_type": relation_type,
            "from_id": trial_record.get("trial_id"),
            "to_id": claim.get("claim_id"),
            "metadata": {
                "verdict": verdict,
                "reviewer": reviewer.get("agent_name"),
                "review_id": review_record.get("review_id"),
            },
        })

        self.store.record_agent_action(self.simulation_id, {
            "action_type": "peer_review",
            "agent_id": reviewer.get("agent_id"),
            "agent_name": reviewer.get("agent_name"),
            "entity_uuid": reviewer.get("entity_uuid"),
            "entity_name": reviewer.get("entity_name"),
            "entity_type": reviewer.get("entity_type"),
            "role": reviewer.get("role"),
            "round_num": round_num,
            "detail": {
                "review_id": review_record.get("review_id"),
                "trial_id": trial_record.get("trial_id"),
                "claim_id": claim.get("claim_id"),
                "verdict": verdict,
                "harness_id": result.trace_id
            },
        })

        return trial_record

    def _run_revision_phase(
        self,
        round_num: int,
        agent: Dict[str, Any],
        original_claim: Dict[str, Any],
        trial: Dict[str, Any],
        simulation_requirement: str,
    ) -> Optional[Dict[str, Any]]:
        """Agent revises a claim after peer feedback via AgentHarness."""
        reviewer = self._find_agent(trial.get("target_agent_id"))
        source_ids = original_claim.get("source_ids", [])
        selected_sources = [
            s for s in self.sources if s.get("source_id") in set(source_ids)
        ]
        source_snippets = _format_source_snippets(selected_sources, max_chars=1000)

        messages = _build_revise_messages(
            agent,
            reviewer,
            original_claim.get("text", ""),
            trial.get("verdict", "needs_revision"),
            trial.get("response", ""),
            source_snippets,
        )

        # Execute through the harness
        result: ActionResult = self.harness.execute(
            action_type=ActionType.VERIFY_CLAIM,
            agent=agent,
            payload={"messages": messages, "context": {"revision_of": original_claim.get("claim_id")}},
            round_num=round_num
        )

        if not result.success:
            logger.warning("AgentHarness VERIFY_CLAIM/REVISE failed for %s", agent.get("agent_name"))
            return None

        # Process the revised text
        revised_text = self._normalize_claim_text(result.data.get("claim", result.raw[:1000]))
        if not self._is_valid_claim_text(revised_text):
            logger.warning(
                "Discarding malformed revision from %s for claim %s",
                agent.get("agent_name"),
                original_claim.get("claim_id"),
            )
            return None

        source_ids = _dedupe_preserve_order(source_ids)

        revised_claim = self.store.record_claim(self.simulation_id, {
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "text": revised_text,
            "source_ids": source_ids,
            "confidence": original_claim.get("confidence", 0.5),
            "status": "revised",
            "round_num": round_num,
            "revision_of": original_claim.get("claim_id"),
        })

        # Provenance: revision updates original
        self.store.record_relation(self.simulation_id, {
            "relation_type": "updates",
            "from_id": revised_claim.get("claim_id"),
            "to_id": original_claim.get("claim_id"),
            "metadata": {"trigger_trial_id": trial.get("trial_id")},
        })

        self.store.record_agent_action(self.simulation_id, {
            "action_type": "revise_claim",
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "round_num": round_num,
            "detail": {
                "original_claim_id": original_claim.get("claim_id"),
                "revised_claim_id": revised_claim.get("claim_id"),
                "trial_id": trial.get("trial_id"),
            },
        })

        with self._claims_lock:
            self._claims.append(revised_claim)
        return revised_claim

    def _run_synthesis_phase(
        self,
        round_num: int,
        agent: Dict[str, Any],
        related_claims: List[Dict[str, Any]],
        simulation_requirement: str,
    ) -> Optional[Dict[str, Any]]:
        """Agent synthesizes multiple related claims into a consolidated finding via AgentHarness."""
        claims_text = "\n".join(
            f"- [{c.get('claim_id', '?')}] (conf={c.get('confidence', '?')}): "
            f"{c.get('text', '')[:300]}"
            for c in related_claims
        )

        messages = _build_synthesis_messages(agent, claims_text, simulation_requirement, config_mode=self.config_mode)

        # Execute through the harness
        result: ActionResult = self.harness.execute(
            action_type=ActionType.PROPOSE_CLAIM,
            agent=agent,
            payload={"messages": messages, "context": {"related_claim_ids": [c.get("claim_id") for c in related_claims]}},
            round_num=round_num
        )

        if not result.success:
            logger.warning("AgentHarness SYNTHESIS failed for %s", agent.get("agent_name"))
            return None

        # Extract synthesized data
        # Use full raw output for synthesis — JSON output should not be truncated
        claim_text = result.data.get("claim", result.raw)
        confidence = result.data.get("confidence", result.data.get("confidence_score", 0.7))

        # Normalize and validate the synthesized claim
        synth_text = self._normalize_claim_text(claim_text)
        if not self._is_valid_claim_text(synth_text):
            logger.warning(
                "Discarding malformed synthesis from %s in round %d",
                agent.get("agent_name"),
                round_num,
            )
            return None

        # Merge source_ids from constituent claims
        all_source_ids: List[str] = []
        seen: set[str] = set()
        for c in related_claims:
            for sid in c.get("source_ids", []):
                if sid and sid not in seen:
                    all_source_ids.append(sid)
                    seen.add(sid)

        synth_record = self.store.record_claim(self.simulation_id, {
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "text": synth_text,
            "source_ids": all_source_ids,
            "confidence": confidence,
            "status": "synthesized",
            "round_num": round_num,
        })

        # Provenance: synthesis derived_from each constituent claim
        for c in related_claims:
            self.store.record_relation(self.simulation_id, {
                "relation_type": "derived_from",
                "from_id": synth_record.get("claim_id"),
                "to_id": c.get("claim_id"),
                "metadata": {"phase": "synthesis"},
            })

        self.store.record_agent_action(self.simulation_id, {
            "action_type": "synthesize",
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "round_num": round_num,
            "detail": {
                "synthesized_claim_id": synth_record.get("claim_id"),
                "constituent_claim_ids": [
                    c.get("claim_id") for c in related_claims
                ],
            },
        })

        with self._claims_lock:
            self._claims.append(synth_record)
            self._unique_sources_cited.update(s for s in all_source_ids if s)
        return synth_record

    # ------------------------------------------------------------------
    # Web search support
    # ------------------------------------------------------------------

    def _get_web_client(self) -> Any:
        """Lazily create the WebSearchClient with quality configuration. Returns None if unavailable."""
        if self._web_search_checked:
            return self._web_search_client
        self._web_search_checked = True
        try:
            from .web_search_client import WebSearchClient

            client = WebSearchClient(api_key=Config.TAVILY_API_KEY, quality_config=self.quality_config)
            if client.is_available():
                self._web_search_client = client
                logger.info("Web search client initialised with quality controls: %s", self.quality_config)
            else:
                logger.info("Web search unavailable — Tavily not configured")
        except Exception as exc:
            logger.warning("Failed to create web search client: %s", exc)
        return self._web_search_client

    @staticmethod
    def _agent_has_action(agent: Dict[str, Any], action: str) -> bool:
        """Verify if agent is authorized to perform a specific action."""
        if not agent:
            return False
        
        # Actions are typically stored in agent["actions"] from Stage 4/5 generation
        agent_actions = agent.get("actions", [])
        if not agent_actions:
            return True # Fallback for legacy rosters
            
        return action.upper() in [a.upper() for a in agent_actions]

    def _generate_search_queries(
        self, agent: Dict[str, Any], simulation_requirement: str, round_num: int,
    ) -> List[str]:
        """LLM generates 2-3 search queries tailored to agent's role."""
        messages = _build_search_query_messages(agent, simulation_requirement, round_num, config_mode=self.config_mode)
        queries: List[str] = []
        try:
            raw_payload = self.llm.chat_json(messages=messages, temperature=0.2, max_tokens=300)
            json_queries = raw_payload.get("search_queries", [])
            if isinstance(json_queries, list) and json_queries:
                queries = [str(q).strip()[:120] for q in json_queries[:3] if str(q).strip()]
            raw = json.dumps(raw_payload, ensure_ascii=False)
            
            # Sanitization Step 1: Reject obvious non-query artifacts
            if not raw or len(raw.strip()) < 5:
                return []
            
            # Sanitization Step 2: Extract JSON object using regex - try multiple patterns
            json_match = None
            for pattern in [
                r'\{[^{}]*\{[^{}]*\}[^{}]*\}',  # nested objects
                r'\{.*\}',  # simple objects
            ]:
                match = re.search(pattern, raw.strip(), re.DOTALL)
                if match:
                    json_match = match
                    break
            
            if json_match:
                try:
                    plan = json.loads(json_match.group(0))
                    json_queries = plan.get("search_queries", [])
                    
                    if isinstance(json_queries, list) and json_queries:
                        queries = [str(q).strip()[:120] for q in json_queries[:3] if str(q).strip()]
                except Exception as e:
                    logger.debug(f"JSON parsing failed: {e}, raw: {raw[:200]}...")
            
            # Sanitization Step 3: Fallback parse if JSON failed by looking for list items
            if not queries:
                for line in raw.strip().splitlines():
                    clean_line = re.sub(r"^\s*[\d\-\.\)\*\"\'\[\]\,]+\s*", "", line).strip()
                    # skip markdown and intro phrases
                    if len(clean_line) > 10 and not clean_line.lower().startswith((
                        "here", "sure", "i am", "my queries", "queries", 
                        "according", "json", "note", "the user", "knowledge",
                        "i will", "as an", "based on", "i'll"
                    )) and not clean_line.endswith("?"):
                        queries.append(clean_line[:120].strip("',\""))

        except Exception as e:
            logger.warning(
                "LLM search-query generation failed for %s — using fallback. Error: %s",
                agent.get("agent_name"), str(e)
            )

        # Final Deduplication and Sanitization
        final_queries = []
        seen = set()
        for q in queries:
            q_norm = q.lower().strip()
            # Reject apology text or generic filler
            if any(ref in q_norm for ref in ["apologize", "sorry", "cannot fulfill", "instead", "here is"]):
                continue
            if q_norm and q_norm not in seen:
                final_queries.append(q)
                seen.add(q_norm)

        if final_queries:
            return final_queries[:3]
            
        # Hard fallback: construct a query from their responsibility to ensure unique paths
        role = agent.get("research_role") or agent.get("role") or "expert"
        goal = agent.get("responsibility") or simulation_requirement
        return [f"{role} {f'{goal[:80]} evidence' if goal else 'latest facts'}"[:120].strip()]

    def _execute_search_query(
        self,
        agent: Dict[str, Any],
        query: str,
        round_num: int,
    ) -> List[Dict[str, Any]]:
        """Execute a SEARCH_WEB intent emitted from a reasoning turn."""
        normalized_query = (query or "").strip()
        if not normalized_query:
            return []

        web_client = self._get_web_client()
        if web_client is None:
            return []

        logger.info(
            "Executing deferred SEARCH_WEB intent for %s: '%s' (Round %d)",
            agent.get("agent_name"),
            normalized_query,
            round_num,
        )

        csi_sources = web_client.search_as_csi_sources(
            query=normalized_query,
            agent_name=agent.get("agent_name"),
            round_num=round_num,
            max_results=3,
            search_depth="basic",
            provider_mode="groq_only",
        )
        if not csi_sources and web_client.is_tavily_available():
            logger.info("Groq search yielded 0 results; falling back to Tavily for query: '%s'", normalized_query)
            csi_sources = web_client.search_as_csi_sources(
                query=normalized_query,
                agent_name=agent.get("agent_name"),
                round_num=round_num,
                max_results=3,
                search_depth="advanced",
                provider_mode="tavily_only",
            )
        return csi_sources

    def _extract_atomic_claims(self, text_chunk: str, source_title: str) -> str:
        """Map raw web chunk to structured atomic claims."""
        if not text_chunk or len(text_chunk.strip()) < 50:
            return text_chunk
            
        system_msg = (
            "You are a precision information extraction system. "
            "Your job is to read raw source text and extract every distinct, factual, and relevant claim.\n"
            "For each claim, you MUST include the exact direct quote from the text that proves it.\n"
            "Respond ONLY with a valid JSON array. Do not include markdown blocks or any other text.\n"
            "Format: [{\"claim\": \"...\", \"direct_quote\": \"...\"}]"
        )
        user_msg = f"Source Title: {source_title}\nSource Text: {text_chunk}\n\nExtract atomic claims as JSON."
        
        try:
            raw = self.llm.chat(
                messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}],
                temperature=0.3,
                max_tokens=2048,
            )
            
            extracted = []
            for pattern in [r'\[\s*\{.*\}\s*\]']:
                m = re.search(pattern, raw.strip(), re.DOTALL)
                if m:
                    try:
                        extracted = json.loads(m.group(0))
                        break
                    except json.JSONDecodeError:
                        continue
            
            if not extracted:
                return text_chunk  # Fallback to raw text if parsing fails
                
            formatted_lines = []
            for item in extracted:
                c = item.get("claim", "")
                q = item.get("direct_quote", "")
                if c and q:
                    formatted_lines.append(f"- FACT: {c}\n  QUOTE: \"{q}\"")
                    
            if not formatted_lines:
                return text_chunk
                
            return "\n\n".join(formatted_lines)
            
        except Exception as e:
            logger.warning(f"Failed to extract atomic claims: {e}")
            return text_chunk  # Failsafe: return raw text

    def _ingest_web_results(
        self,
        simulation_id: str,
        results: List[Dict[str, Any]],
        agent: Dict[str, Any],
        round_num: int,
        search_query: Optional[str] = None,
        discovery_kind: str = "agent_search",
    ) -> List[Dict[str, Any]]:
        """Convert web search results into CSI sources, chunking large texts, add to self.sources, and
        record them in the store's sources index. 
        
        Observability: Returns newly ingested sources and logs duplication stats."""
        ingested: List[Dict[str, Any]] = []
        duplicate_count = 0
        total_results = len(results)

        with self._sources_lock:
            existing_ids = {s.get("source_id") for s in self.sources}
            existing_urls = {
                _normalize_source_url(s.get("url", ""))
                for s in self.sources
                if s.get("url")
            }

        for src in results:
            normalized_url = _normalize_source_url(src.get("url", ""))
            if normalized_url and normalized_url in existing_urls:
                duplicate_count += 1
                continue

            content = src.get("content", "")
            # Robust non-LLM chunking using TextProcessor utilities
            # Optimized: Increased chunk size to 2000 to reduce total source IDs, 
            # while maintaining overlap for coherence.
            chunks = TextProcessor.split_text(TextProcessor.preprocess_text(content), chunk_size=2000, overlap=200)
            if not chunks and content.strip():
                chunks = [content.strip()]
            
            base_id = src.get("source_id", uuid.uuid4().hex[:12])
            
            # Limit number of chunks per source to 5 to prevent ID explosion from huge pages
            chunks = chunks[:5]
            
            for i, chunk in enumerate(chunks):
                sid = f"{base_id}_part{i+1}" if len(chunks) > 1 else base_id
                
                if sid in existing_ids:
                    continue  # deduplicate
                
                chunk_src = src.copy()
                title = f"{src.get('title', 'Unknown Source')} (Part {i+1}/{len(chunks)})" if len(chunks) > 1 else src.get('title', 'Unknown Source')
                chunk_src["source_id"] = sid
                chunk_src["title"] = title
                metadata = chunk_src.get("metadata") if isinstance(chunk_src.get("metadata"), dict) else {}
                metadata = dict(metadata)
                metadata["discovery"] = {
                    "kind": discovery_kind,
                    "agent_id": agent.get("agent_id"),
                    "agent_name": agent.get("agent_name") or agent.get("entity_name"),
                    "role": agent.get("role"),
                    "round_num": round_num,
                    "prompt": search_query or metadata.get("prompt") or src.get("query") or "",
                    "provider_mode": src.get("provider_mode") or metadata.get("provider_mode") or "",
                    "search_depth": src.get("search_depth") or metadata.get("search_depth") or "",
                }
                chunk_src["metadata"] = metadata
                chunk_src.setdefault("origin", discovery_kind)
                
                # Assign raw chunk content directly to atomic_claims to avoid LLM overhead during ingestion
                # This ensures the raw data is immediately available to all agents for extraction
                chunk_src["content"] = chunk
                chunk_src["atomic_claims"] = chunk
                
                # Ensure required fields
                chunk_src.setdefault("created_at", "")
                chunk_src.setdefault("updated_at", "")

                with self._sources_lock:
                    if sid in existing_ids:
                        continue  # deduplicate in case another thread added same id
                    if normalized_url and normalized_url in existing_urls:
                        continue
                    self.sources.append(chunk_src)
                    existing_ids.add(sid)
                    if normalized_url:
                        existing_urls.add(normalized_url)
                ingested.append(chunk_src)

        # Persist to the store's sources index atomically.
        if ingested:
            try:
                if hasattr(self.store, "merge_sources"):
                    self.store.merge_sources(simulation_id, ingested)
                else:
                    idx = self.store._load_sources_index(simulation_id)
                    idx_sources = idx.get("sources", [])
                    idx_sources.extend(ingested)
                    idx["sources"] = idx_sources
                    idx["source_count"] = len(idx_sources)
                    self.store._save_sources_index(simulation_id, idx)
            except Exception as exc:
                logger.warning("Failed to persist web sources to index: %s", exc)

        logger.info(
            f"[CSI-INGEST] SimID: {simulation_id} | Agent: {agent.get('agent_name')} | "
            f"Results: {total_results} | Duplicates: {duplicate_count} | NewChunks: {len(ingested)}"
        )
        return ingested

    def _run_exploration_phase(
        self,
        round_num: int,
        agent: Dict[str, Any],
        simulation_requirement: str,
    ) -> List[Dict[str, Any]]:
        """Agent searches the web based on their role and the query.

        Only runs for agents with SEARCH_WEB in world_actions.
        Returns list of discovered sources that were ingested into CSI store.
        """
        if not self._agent_has_action(agent, "SEARCH_WEB"):
            return []

        web_client = self._get_web_client()
        if web_client is None:
            return []

        agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
        
        # --- Deep Research: Task Decomposition & Working Plan setup via JSON structure
        queries = self._generate_search_queries(agent, simulation_requirement, round_num)
        all_discovered: List[Dict[str, Any]] = []
        consecutive_failures = 0

        for idx, base_query in enumerate(queries):
            query = base_query
            
            # --- Deep Research: Breadth & Depth Search iteration
            max_reflection_attempts = 2
            for attempt in range(max_reflection_attempts):
                # Unlimited ingestion: Fetch all available information from the search
                # results. Ingestion itself is raw/low-cost (no LLM).
                csi_sources = web_client.search_as_csi_sources(
                    query=query,
                    agent_name=agent_name,
                    round_num=round_num,
                    max_results=5,  # Reduced from 30 - agents only need top 5 relevant sources per query
                    search_depth="advanced",
                    provider_mode="groq_only",
                )

                ingested = self._ingest_web_results(
                    self.simulation_id,
                    csi_sources,
                    agent,
                    round_num,
                    search_query=query,
                    discovery_kind="agent_search",
                )

                # Record the SEARCH_WEB action
                self.store.record_agent_action(self.simulation_id, {
                    "action_type": "SEARCH_WEB",
                    "agent_id": agent.get("agent_id"),
                    "agent_name": agent_name,
                    "entity_uuid": agent.get("entity_uuid"),
                    "entity_name": agent.get("entity_name"),
                    "entity_type": agent.get("entity_type"),
                    "role": agent.get("role"),
                    "round_num": round_num,
                    "detail": {
                        "query": query,
                        "results_count": len(csi_sources),
                        "ingested_count": len(ingested),
                        "urls": [r.get("url", "") for r in csi_sources],
                        "deep_research_attempt": attempt + 1,
                    },
                })

                all_discovered.extend(ingested)
                logger.info(
                    "Agent %s SEARCH_WEB: query='%s' found=%d ingested=%d (Attempt %d)",
                    agent_name, query, len(csi_sources), len(ingested), attempt + 1
                )

                # --- Deep Research: Self Reflection (Low-level reflection)
                if len(csi_sources) == 0:
                    consecutive_failures += 1
                    logger.warning("Agent %s: Zero results for '%s'. Reflecting failure and retrying...", agent_name, query)
                    # Simple reflection modification: abstract heavily to broader keywords by removing edge chars
                    tokens = [t for t in query.split() if len(t) > 3]
                    if len(tokens) > 1:
                        query = " ".join(tokens[:-1]) + " latest news overview"
                    else:
                        query = f"{simulation_requirement[:40]} {agent.get('research_role', 'expert')} latest news overview"
                    continue # Retry search
                
                # Success or standard path; no reflection needed
                consecutive_failures = 0
                break

        return all_discovered

    def _run_deep_read_phase(
        self,
        round_num: int,
        agent: Dict[str, Any],
        urls: List[str],
    ) -> List[Dict[str, Any]]:
        """Agent deep-reads specific URLs. Only for agents with READ_URL in
        world_actions."""
        if not self._agent_has_action(agent, "READ_URL"):
            return []

        web_client = self._get_web_client()
        if web_client is None:
            return []
        if not urls:
            return []

        agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"

        csi_sources = web_client.extract_as_csi_sources(
            urls=urls[:3],
            agent_name=agent_name,
            round_num=round_num,
        )

        ingested = self._ingest_web_results(
            self.simulation_id,
            csi_sources,
            agent,
            round_num,
            search_query=", ".join(urls[:3]),
            discovery_kind="read_url",
        )

        # Record READ_URL action
        self.store.record_agent_action(self.simulation_id, {
            "action_type": "READ_URL",
            "agent_id": agent.get("agent_id"),
            "agent_name": agent_name,
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "round_num": round_num,
            "detail": {
                "urls": urls[:3],
                "extracted_count": len(ingested),
            },
        })

        logger.info(
            "Agent %s READ_URL: %d urls, extracted=%d",
            agent_name, len(urls), len(ingested),
        )
        return ingested

    def _select_urls_for_deep_read(
        self,
        agent: Dict[str, Any],
        search_results: List[Dict[str, Any]],
        simulation_requirement: str,
    ) -> List[str]:
        """Use LLM to pick 1-2 URLs from search results for deep reading."""
        if not search_results:
            return []

        messages = _build_deep_read_selection_messages(
            agent, search_results, simulation_requirement,
        )
        try:
            raw = self.llm.chat(messages=messages, temperature=0.3, max_tokens=50)
        except Exception:
            logger.warning("LLM URL selection failed — picking first result")
            return [search_results[0].get("url", "")] if search_results else []

        # Parse numbers from response
        indices: List[int] = []
        for match in re.finditer(r"\d+", raw):
            idx = int(match.group()) - 1  # 1-based to 0-based
            if 0 <= idx < len(search_results):
                indices.append(idx)
        if not indices:
            indices = [0]

        return [
            search_results[i].get("url", "")
            for i in indices[:2]
            if search_results[i].get("url")
        ]

    # ------------------------------------------------------------------
    # Gate policy
    # ------------------------------------------------------------------

    def _check_gate_policy(self) -> bool:
        """Return True when gate conditions are satisfied and rounds can stop
        early."""
        if len(self._unique_sources_cited) < self._min_source_coverage:
            return False
        if self._reviewed_ratio() < self._min_reviewed_ratio:
            return False
        for c in self._claims:
            if not self._is_valid_claim_text(c.get("text", "")):
                return False
        if self._block_on_missing_provenance:
            # Every claim must have at least one derived_from relation.
            # We approximate by checking that all claims cite at least one source.
            for c in self._claims:
                if not c.get("source_ids"):
                    return False
        return True

    # ------------------------------------------------------------------
    # Reviewer selection
    # ------------------------------------------------------------------

    def _pick_reviewer(
        self,
        proposer: Dict[str, Any],
        claim: Dict[str, Any],
        exclude_agent_ids: Optional[set] = None,
    ) -> Optional[Dict[str, Any]]:
        """Select a peer reviewer based on challenge targets and workload.
        
        Args:
            proposer: The agent who proposed the claim.
            claim: The claim metadata.
            exclude_agent_ids: Optional set of agent_ids to skip (e.g. already selected).
        """
        proposer_id = proposer.get("agent_id")
        challenge_targets = proposer.get("challenge_targets", [])
        exclude = exclude_agent_ids or set()
        exclude.add(proposer_id)

        # Normalize challenge targets for fuzzy matching
        normalized_targets = {
            t.replace("_", "-").lower() for t in challenge_targets
        }

        # First pass: find a reviewer whose research_role is a challenge target
        candidates: List[Dict[str, Any]] = []
        for agent in self.roster:
            if agent.get("agent_id") in exclude:
                continue
            role_normalized = (agent.get("research_role") or "").replace("_", "-").lower()
            if role_normalized in normalized_targets:
                candidates.append(agent)

        if candidates:
            # Pick the one who has reviewed the fewest claims so far to balance workload
            review_counts: Dict[Any, int] = {}
            for t in self._trials:
                tid = t.get("target_agent_id")
                review_counts[tid] = review_counts.get(tid, 0) + 1
            candidates.sort(key=lambda a: review_counts.get(a.get("agent_id"), 0))
            return candidates[0]

        # Fallback 1: different research_role
        for agent in self.roster:
            if agent.get("agent_id") in exclude:
                continue
            if (agent.get("research_role") or "").lower() != (proposer.get("research_role") or "").lower():
                return agent

        # Fallback 2: anyone not excluded
        for agent in self.roster:
            if agent.get("agent_id") not in exclude:
                return agent

        return None

    # ------------------------------------------------------------------
    # Source selection (mirrors simulation_csi_local.py)
    # ------------------------------------------------------------------

    def _agent_query_terms(
        self, agent: Dict[str, Any], simulation_requirement: str
    ) -> List[str]:
        """Build query terms incorporating responsibility and research_role."""
        parts = [
            agent.get("role", ""),
            agent.get("responsibility", ""),
            agent.get("research_role", ""),
            " ".join(agent.get("skills", []) or []),
            " ".join(agent.get("research_focus", []) or []),
            agent.get("entity_name", ""),
            agent.get("entity_type", ""),
            agent.get("entity_summary", ""),
            simulation_requirement or "",
        ]
        return self._tokenize(" ".join(parts))

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
        stopwords = {
            "the", "and", "or", "of", "to", "in", "a", "an", "for", "with",
            "on", "is", "are", "be", "this", "that", "by", "from", "as", "at",
            "it", "into", "we", "our", "their", "your", "can", "will",
            "should", "must",
        }
        return [t for t in tokens if len(t) > 1 and t not in stopwords]

    def _score_source(
        self, source: Dict[str, Any], query_terms: List[str]
    ) -> float:
        """Enhanced source scoring with quality validation."""
        # Base score from existing logic
        haystack = " ".join([
            str(source.get("title", "")),
            str(source.get("summary", "")),
            str(source.get("content", "")),
            " ".join(source.get("keywords", []) or []),
        ]).lower()
        score = float(source.get("priority", 0.0) or 0.0)
        
        # Keyword relevance scoring
        for term in query_terms:
            if term in haystack:
                score += 1.0
        
        # Source type bonuses
        if source.get("source_type") == "requirement":
            score += 1.25
        elif source.get("source_type") == "document_chunk":
            score += 0.5
        
        # Quality validation bonus/penalty
        quality_check = source.get("metadata", {}).get("quality_check")
        if quality_check:
            if quality_check.get("valid", True):
                # Bonus for valid sources
                score += 0.5
                # Additional bonus for news-like content
                if quality_check.get("has_news_indicators", False):
                    score += 0.3
            else:
                # Penalty for invalid sources (shouldn't happen but safety check)
                score -= 1.0
        
        # Content length bonus (prefer substantial content)
        content_length = len(str(source.get("content", "")))
        if content_length > 1000:
            score += 0.2
        elif content_length < 200:
            score -= 0.3
        
        # Recency bonus for web sources (rough heuristic)
        if source.get("source_type") == "web":
            url = str(source.get("url", ""))
            # Prefer HTTPS
            if url.startswith("https://"):
                score += 0.1
            # Prefer established domains (basic heuristic)
            domain_indicators = ['.edu', '.gov', '.org', 'news', 'times', 'bbc', 'reuters']
            if any(indicator in url.lower() for indicator in domain_indicators):
                score += 0.2
        
        return max(0.0, score)  # Ensure non-negative score

    def _select_sources(
        self,
        sources: List[Dict[str, Any]],
        query_terms: List[str],
        limit: int = 3,
        blackboard_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Select highest-quality sources for investigation, with re-validation and novelty preference."""
        # Re-validate sources if they don't have quality metadata
        validated_sources = []
        for src in sources:
            if src.get("metadata", {}).get("quality_check"):
                # Already validated
                validated_sources.append(src)
            elif src.get("source_type") == "web":
                # Re-validate web sources that slipped through
                from .web_search_client import _validate_source_quality
                quality_check = _validate_source_quality(
                    src.get("title", ""),
                    src.get("url", ""),
                    src.get("content", ""),
                    float(src.get("priority", 0.5))
                )
                if quality_check["valid"]:
                    # Update source with quality metadata
                    src["metadata"] = src.get("metadata", {})
                    src["metadata"]["quality_check"] = quality_check
                    src["priority"] = quality_check["quality_score"]
                    validated_sources.append(src)
                else:
                    logger.debug("Filtered out low-quality source during selection: %s", src.get("title", "")[:50])
            else:
                # Non-web sources pass through
                validated_sources.append(src)
        
        # Rank by enhanced scoring
        # Penalty for already cited sources to encourage exploration of all chunks
        def _score_with_novelty(s: Dict[str, Any]) -> float:
            base = self._score_source(s, query_terms)
            sid = s.get("source_id")
            # If this source id has been used in self._unique_sources_cited, apply a slight penalty
            # so other agents look at the 'tail' of the research pool.
            if sid in self._unique_sources_cited:
                base *= 0.4  # Significant penalty to force novelty
            if blackboard_context:
                contradicted_source_ids = blackboard_context.get("contradicted_source_ids") or set()
                supported_source_ids = blackboard_context.get("supported_source_ids") or set()
                reviewed_source_ids = blackboard_context.get("unique_source_ids") or set()
                if sid in contradicted_source_ids:
                    base *= 0.35
                elif sid in supported_source_ids:
                    base += 0.5
                elif sid not in reviewed_source_ids:
                    base += 0.15
            return base

        ranked = sorted(
            validated_sources,
            key=_score_with_novelty,
            reverse=True,
        )
        
        selected = ranked[:max(1, limit)]
        logger.debug(
            "Selected %d/%d sources for investigation (avg score: %.2f)",
            len(selected), len(validated_sources),
            sum(self._score_source(s, query_terms) for s in selected) / max(1, len(selected))
        )
        
        return selected

    # ------------------------------------------------------------------
    # Template fallbacks (from simulation_csi_local.py)
    # ------------------------------------------------------------------

    @staticmethod
    def _template_draft_claim(
        agent: Dict[str, Any],
        sources: List[Dict[str, Any]],
        round_num: int,
    ) -> str:
        primary = sources[0] if sources else {}
        primary_title = primary.get("title", "input data")
        primary_summary = primary.get("summary", "") or primary.get("content", "")[:220]
        role = agent.get("role") or "investigator"
        name = (
            agent.get("agent_name")
            or agent.get("entity_name")
            or f"Agent {agent.get('agent_id')}"
        )
        if primary_summary:
            return (
                f"CLAIM: {name} ({role}) infers that {primary_title} indicates: "
                f"{primary_summary[:220]}\n"
                f"CONFIDENCE: 0.5\n"
                f"EVIDENCE: Based on source '{primary_title}'"
            )
        return (
            f"CLAIM: {name} ({role}) proposes a claim for round {round_num} "
            f"grounded in the available input data.\n"
            f"CONFIDENCE: 0.4\n"
            f"EVIDENCE: General input data"
        )

    def _template_peer_response(
        self,
        proposer: Dict[str, Any],
        reviewer: Dict[str, Any],
        sources: List[Dict[str, Any]],
        claim_text: str,
    ) -> Tuple[str, str]:
        """Keyword-overlap heuristic from the original bootstrap."""
        agent_terms = set(self._agent_query_terms(proposer, claim_text))
        peer_terms = set(self._agent_query_terms(reviewer, claim_text))
        overlap = len(agent_terms & peer_terms)
        evidence_strength = sum(
            1 for src in sources if float(src.get("priority", 0) or 0) >= 0.8
        )
        if overlap >= 5 and evidence_strength >= 2:
            return (
                "supports",
                "Peer review agrees that the claim is well grounded and "
                "sufficiently evidenced.",
            )
        if overlap >= 3:
            return (
                "needs_revision",
                "Peer review requests tighter wording and stronger source "
                "linkage.",
            )
        return (
            "contradicts",
            "Peer review flags the claim as under-evidenced or too broad.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_agent(self, agent_id: Any) -> Dict[str, Any]:
        """Look up an agent from the roster by agent_id."""
        for agent in self.roster:
            if agent.get("agent_id") == agent_id:
                return agent
        return {"agent_id": agent_id, "agent_name": f"Agent {agent_id}"}

    @staticmethod
    def _normalize_claim_text(text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return ""

        if "<execute_tool>" in cleaned or '"name": "web.run"' in cleaned or '"name": "browser.search"' in cleaned or '"name": "browser.run"' in cleaned:
            return ""

        extracted = _extract_field(cleaned, "CLAIM")
        if extracted:
            cleaned = extracted.strip()

        cleaned = re.sub(r"^\*\*CLAIM:\*\*\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^CLAIM:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n\s*\*\*EVIDENCE:\*\*.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"\n\s*EVIDENCE:.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"\n\s*\*\*CONFIDENCE:\*\*.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"\n\s*CONFIDENCE:.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"\s+\*\*EVIDENCE:\*\*.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+EVIDENCE:.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+\*\*CONFIDENCE:\*\*.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+CONFIDENCE:.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def _is_valid_claim_text(cls, text: str) -> bool:
        cleaned = cls._normalize_claim_text(text)
        if len(cleaned) < 40:
            return False
        if cleaned.startswith("{") and cleaned.endswith("}"):
            return False
        return True

    @staticmethod
    def _normalize_reasoning_text(text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return ""
        if "<execute_tool>" in cleaned or '"name": "web.run"' in cleaned or '"name": "browser.search"' in cleaned or '"name": "browser.run"' in cleaned:
            return ""
        return re.sub(r"\s+", " ", cleaned).strip()

    def _reviewed_ratio(self) -> float:
        """Fraction of claims that have at least one trial."""
        valid_claims = [c for c in self._claims if self._is_valid_claim_text(c.get("text", ""))]
        if not valid_claims:
            return 1.0
        reviewed_ids = {t.get("claim_id") for t in self._trials}
        reviewed = sum(
            1 for c in valid_claims if c.get("claim_id") in reviewed_ids
        )
        return reviewed / len(valid_claims)

    def _unreviewed_ratio(self) -> float:
        return 1.0 - self._reviewed_ratio()

    # ------------------------------------------------------------------
    # Phase 4: State Preservation — Reusable Blueprints
    # ------------------------------------------------------------------

    def _save_blueprint(self, simulation_requirement: str) -> None:
        """Persist the current research state as a reusable blueprint.

        Saves resolved claims, trials, sources, and the full CSI graph snapshot
        so future runs on the same or related topics can skip Step 2 entirely
        and resume from the existing knowledge base.
        """
        try:
            import os

            sim_dir = self.store._sim_dir(self.simulation_id)
            blueprint_path = os.path.join(sim_dir, "csi", "blueprint.json")

            # Categorise claims by resolution status
            reviewed_ids = {t.get("claim_id") for t in self._trials}
            supported_ids: set[str] = set()
            contradicted_ids: set[str] = set()
            for trial in self._trials:
                cid = trial.get("claim_id")
                v = trial.get("verdict", "")
                if v == "supports":
                    supported_ids.add(cid)
                elif v == "contradicts":
                    contradicted_ids.add(cid)

            resolved_claims = []
            for claim in self._claims:
                cid = claim.get("claim_id", "")
                status = claim.get("status", "proposed")
                if cid in supported_ids:
                    resolution = "verified"
                elif cid in contradicted_ids:
                    resolution = "debunked"
                elif status == "synthesized":
                    resolution = "synthesized"
                elif cid in reviewed_ids:
                    resolution = "reviewed"
                else:
                    resolution = "unreviewed"

                resolved_claims.append({
                    "claim_id": cid,
                    "text": claim.get("text", ""),
                    "confidence": claim.get("confidence", 0.5),
                    "source_ids": claim.get("source_ids", []),
                    "agent_name": claim.get("agent_name", ""),
                    "status": status,
                    "resolution": resolution,
                })

            blueprint = {
                "simulation_id": self.simulation_id,
                "simulation_requirement": simulation_requirement,
                "created_at": __import__("datetime").datetime.now().isoformat(),
                "total_claims": len(self._claims),
                "total_trials": len(self._trials),
                "total_sources": len(self.sources),
                "unique_sources_cited": len(self._unique_sources_cited),
                "resolved_claims": resolved_claims,
                "source_ids": [s.get("source_id") for s in self.sources if s.get("source_id")],
                "roster_summary": [
                    {
                        "agent_id": a.get("agent_id"),
                        "agent_name": a.get("agent_name"),
                        "research_role": a.get("research_role") or a.get("role"),
                        "responsibility": a.get("responsibility"),
                    }
                    for a in self.roster
                ],
            }

            os.makedirs(os.path.dirname(blueprint_path), exist_ok=True)
            with open(blueprint_path, "w", encoding="utf-8") as f:
                json.dump(blueprint, f, ensure_ascii=False, indent=2)

            logger.info(
                "Blueprint saved: %d claims (%d verified, %d debunked), %d sources",
                len(resolved_claims),
                len(supported_ids),
                len(contradicted_ids),
                len(self.sources),
            )
        except Exception as exc:
            logger.warning("Failed to save blueprint: %s", exc)

    @staticmethod
    def load_blueprint(csi_store: Any, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Load a previously saved blueprint for a simulation.

        Returns the blueprint dict if found, or None. Callers can use this to
        check whether a prior research run exists and decide whether to skip
        the seed search / reuse existing knowledge.
        """
        import os
        try:
            sim_dir = csi_store._sim_dir(simulation_id)
            blueprint_path = os.path.join(sim_dir, "csi", "blueprint.json")
            if os.path.exists(blueprint_path):
                with open(blueprint_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load blueprint for %s: %s", simulation_id, exc)
        return None
