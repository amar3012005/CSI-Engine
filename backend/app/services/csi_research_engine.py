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
from .text_processor import TextProcessor

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


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_propose_messages(
    agent: Dict[str, Any],
    source_snippets: str,
    simulation_requirement: str,
    search_feedback: Optional[str] = None,
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
        "IMPORTANT: You have NATIVE ACCESS to the web. If you explicitly LACK the evidence to verify a truth, you MUST perform a RECURSIVE SEARCH to fill your gap.\n\n"
        "Respond with ONLY a raw JSON object choosing ONE of these two actions:\n\n"
        "Action 1 (PROPOSE_CLAIM):\n"
        "{\n"
        '  "action": "propose_claim",\n'
        '  "claim": "Your specific finding (2-4 sentences, matching your profession\'s tone)",\n'
        '  "confidence": 0.95,\n'
        '  "evidence": "Which specific sources support this"\n'
        "}\n\n"
        "Action 2 (SEARCH_WEB):\n"
        "{\n"
        '  "action": "search_web",\n'
        '  "search_query": "highly technical keyword phrase based on your profession",\n'
        '  "reasoning": "I need evidence about [X] from a [Profession] perspective"\n'
        "}"
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
        "Action 1 (CHALLENGE_CLAIM / VERIFY):\n"
        "{\n"
        '  "action": "peer_review",\n'
        '  "verdict": "supports" OR "contradicts" OR "needs_revision",\n'
        '  "reasoning": "Scientific/Profession-driven reasoning (2-3 sentences)",\n'
        '  "critique": "Specific flaws or missing context identified"\n'
        "}\n\n"
        "Action 2 (Search the Web to DEBUNK or VALIDATE):\n"
        "{\n"
        '  "action": "search_web",\n'
        '  "search_query": "specific context or counter-argument needed from your profession\'s angle",\n'
        '  "reasoning": "I need to verify this specific fact before ruling"\n'
        "}"
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


    async def _run_synthesis_phase(
        self,
        agent: Dict[str, Any],
        claims: List[Dict[str, Any]],
        simulation_requirement: str,
        round_num: int,
    ) -> Optional[Dict[str, Any]]:
        """Synthesize multiple claims into a consolidated finding for an agent."""
        if not claims:
            return None

        # Build list of claim texts
        claims_text = "\n".join([f"- {c['text']}" for c in claims])

        messages = self._build_synthesis_messages(agent, claims_text, simulation_requirement)

        try:
            raw = self.llm.chat(messages=messages, temperature=0.3, max_tokens=1024)
            claim_text = _extract_field(raw, "CLAIM") or raw.strip()
            confidence = _extract_confidence(raw)
            evidence = _extract_field(raw, "EVIDENCE")
        except Exception as exc:
            logger.warning("Synthesis failed: %s", exc)
            return None

        # Record as a new claim of kind 'synthesis'
        synth_record = self.store.record_claim(self.simulation_id, {
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "text": claim_text,
            "source_ids": [], # Combined sources from original claims usually
            "confidence": confidence,
            "status": "synthesized",
            "round_num": round_num,
            "metadata": {"evidence_summary": evidence}
        })

        # Link to constituent claims
        for sc in claims:
            self.store.record_relation(self.simulation_id, {
                "relation_type": "synthesized_from",
                "from_id": synth_record.get("claim_id"),
                "to_id": sc.get("claim_id"),
            })

        with self._claims_lock:
            self._claims.append(synth_record)
        return synth_record


def _build_synthesis_messages(
    agent: Dict[str, Any],
    claims_text: str,
    simulation_requirement: str,
) -> List[Dict[str, str]]:
    agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
    research_role = agent.get("research_role") or agent.get("role") or "investigator"

    system_msg = (
        f"You are {agent_name}, a {research_role} and {agent.get('profession', 'expert')}.\n"
        f"Your bio: {agent.get('bio', 'Expert investigator')}.\n"
        "Synthesize these related claims into a consolidated finding."
    )
    user_msg = (
        "Task: Synthesize these related claims into one consolidated finding relevant to: "
        f'"{simulation_requirement}"\n\n'
        f"Claims Data:\n{claims_text}\n\n"
        "This is a low-latency logistics turn. Respond with:\n"
        "1. CLAIM: Your consolidated finding (2-4 sentences)\n"
        "2. CONFIDENCE: 0.0-1.0\n"
        "3. EVIDENCE: Key supporting evidence identifiers"
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_search_query_messages(
    agent: Dict[str, Any],
    simulation_requirement: str,
    round_num: int,
) -> List[Dict[str, str]]:
    """Build messages for generating web search queries from an agent's perspective."""
    agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
    research_role = agent.get("research_role") or agent.get("role") or "investigator"
    responsibility = agent.get("responsibility") or "investigate claims"
    evidence_priority = agent.get("evidence_priority") or "facts and data"

    counter_hint = ""
    if round_num >= 2:
        counter_hint = (
            '\nThis is a later round — focus on finding COUNTER-EVIDENCE, '
            'alternative viewpoints, or verification of previous findings.'
        )

    system_msg = (
        f"You are {agent_name}, a {research_role}. "
        f"Your specific responsibility in this investigation is: {responsibility}. "
        f"Your evidence gathering prioritizes: {evidence_priority}.\n"
        "You use a Deep Research Task Decomposition approach: identify knowledge gaps, draft a working plan, and then output explicit search queries."
    )
    user_msg = (
        "Generate a research strategy to help securely answer the main research question: "
        f'"{simulation_requirement}"\n\n'
        "Include relevant keywords like current year, 'latest', or specific entity names to ensure up-to-date and highly accurate results.\n"
        "Do NOT just copy the main research question. Focus deeply on your unique area of expertise.\n"
        f"{counter_hint}\n"
        "Respond with ONLY a raw JSON object containing three keys: 'knowledge_gaps' (list of strings), 'working_plan' (list of steps), and 'search_queries' (list of 2-3 highly specific search strings).\n"
        "Format precisely:\n"
        "{\n"
        '  "knowledge_gaps": ["gap 1"],\n'
        '  "working_plan": ["step 1"],\n'
        '  "search_queries": ["query 1"]\n'
        "}"
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_search_query_messages(
    agent: Dict[str, Any],
    simulation_requirement: str,
    round_num: int,
) -> List[Dict[str, str]]:
    """Build messages for generating web search queries from an agent's perspective."""
    agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
    research_role = agent.get("research_role") or agent.get("role") or "investigator"
    responsibility = agent.get("responsibility") or "investigate claims"
    evidence_priority = agent.get("evidence_priority") or "facts and data"

    counter_hint = ""
    if round_num >= 2:
        counter_hint = (
            '\nThis is a later round — focus on finding COUNTER-EVIDENCE, '
            'alternative viewpoints, or verification of previous findings.'
        )

    system_msg = (
        f"You are {agent_name}, a {research_role}. "
        f"Your specific responsibility in this investigation is: {responsibility}. "
        f"Your evidence gathering prioritizes: {evidence_priority}.\n"
        "You use a Deep Research Task Decomposition approach: identify knowledge gaps, draft a working plan, and then output explicit search queries."
    )
    user_msg = (
        "Generate a research strategy to help securely answer the main research question: "
        f'"{simulation_requirement}"\n\n'
        "Include relevant keywords like current year, 'latest', or specific entity names to ensure up-to-date and highly accurate results.\n"
        "Do NOT just copy the main research question. Focus deeply on your unique area of expertise.\n"
        f"{counter_hint}\n"
        "Respond with ONLY a raw JSON object containing three keys: 'knowledge_gaps' (list of strings), 'working_plan' (list of steps), and 'search_queries' (list of 2-3 highly specific search strings).\n"
        "Format precisely:\n"
        "{\n"
        '  "knowledge_gaps": ["gap 1"],\n'
        '  "working_plan": ["step 1"],\n'
        '  "search_queries": ["query 1"]\n'
        "}"
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_deep_read_selection_messages(
    agent: Dict[str, Any],
    search_results: List[Dict[str, Any]],
    simulation_requirement: str,
) -> List[Dict[str, str]]:
    """Build messages for selecting URLs to deep-read from search results."""
    agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
    research_role = agent.get("research_role") or agent.get("role") or "investigator"

    urls_block = "\n".join(
        f"[{i+1}] {r.get('title', 'Untitled')} — {r.get('url', '')}"
        for i, r in enumerate(search_results)
    )

    system_msg = f"You are {agent_name}, a {research_role}."
    user_msg = (
        "From these search results, pick 1-2 URLs most worth reading in full "
        f'for the research question: "{simulation_requirement}"\n\n'
        f"{urls_block}\n\n"
        "Respond with just the numbers (e.g. '1, 3'). Nothing else."
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ---------------------------------------------------------------------------
# Source formatting helpers
# ---------------------------------------------------------------------------

def _format_source_snippets(sources: List[Dict[str, Any]], max_chars: int = 3000) -> str:
    """Flatten selected sources into a prompt-friendly text block."""
    parts: List[str] = []
    budget = max_chars
    for idx, src in enumerate(sources, 1):
        title = src.get("title") or f"Source {idx}"
        body = (src.get("summary") or src.get("content") or "")[:600]
        entry = f"[{idx}] {title}: {body}"
        if len(entry) > budget:
            entry = entry[:budget]
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

    def _run_synthesis_phase(
        self,
        round_num: int,
        agent: Dict[str, Any],
        claims: List[Dict[str, Any]],
        simulation_requirement: str,
    ) -> Optional[Dict[str, Any]]:
        """Agent synthesizes multiple claims into a single consolidated finding."""
        claims_text = "\n".join(
            f"- {c.get('text')} (Confidence: {c.get('confidence', 'N/A')})"
            for c in claims
        )
        messages = self._build_synthesis_messages(agent, claims_text, simulation_requirement)

        try:
            raw = self.llm.chat(messages=messages, temperature=0.3, max_tokens=1024)
            claim_text = _extract_field(raw, "CLAIM") or raw.strip()
            confidence = _extract_confidence(raw)
            evidence = _extract_field(raw, "EVIDENCE")
        except Exception as exc:
            logger.warning("Synthesis failed: %s", exc)
            return None

        # Record as a new claim of kind 'synthesis'
        synth_record = self.store.record_claim(self.simulation_id, {
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "text": claim_text,
            "source_ids": [], # Combined sources from original claims usually
            "confidence": confidence,
            "status": "synthesized",
            "round_num": round_num,
            "metadata": {"evidence_summary": evidence}
        })

        # Link to constituent claims
        for sc in claims:
            self.store.record_relation(self.simulation_id, {
                "relation_type": "synthesized_from",
                "from_id": synth_record.get("claim_id"),
                "to_id": sc.get("claim_id"),
            })

        with self._claims_lock:
            self._claims.append(synth_record)
        return synth_record

    def _build_synthesis_messages(
        self,
        agent: Dict[str, Any],
        claims_text: str,
        simulation_requirement: str,
    ) -> List[Dict[str, str]]:
        agent_name = agent.get("agent_name") or agent.get("entity_name") or "Agent"
        research_role = agent.get("research_role") or agent.get("role") or "investigator"

        system_msg = (
            f"You are {agent_name}, a {research_role} and {agent.get('profession', 'expert')}.\n"
            f"Your bio: {agent.get('bio', 'Expert investigator')}.\n"
            "Synthesize these related claims into a consolidated finding."
        )
        user_msg = (
            "Task: Synthesize these related claims into one consolidated finding relevant to: "
            f'"{simulation_requirement}"\n\n'
            f"Claims Data:\n{claims_text}\n\n"
            "This is a low-latency logistics turn. Respond with:\n"
            "1. CLAIM: Your consolidated finding (2-4 sentences)\n"
            "2. CONFIDENCE: 0.0-1.0\n"
            "3. EVIDENCE: Key supporting evidence identifiers"
        )
        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def __init__(
        self,
        simulation_id: str,
        llm_client: LLMClient,
        csi_store: Any,  # SimulationCSILocalStore
        sources: List[Dict[str, Any]],
        roster: List[Dict[str, Any]],
        config: Any,  # ResearchWorkflowConfig
        quality_config: Dict[str, Any] | None = None,
    ) -> None:
        self.simulation_id = simulation_id
        self.llm = llm_client
        self.store = csi_store
        self.sources = sources
        self.roster = roster
        self.config = config
        self.quality_config = quality_config or {
            "min_content_length": 50,   # HIVEMIND Core returns shorter snippets
            "min_title_length": 3,
            "min_search_score": 0.1,
            "require_news_indicators": False,  # Snippets often lack news phrases
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

        # Track web sources discovered during exploration for deep-read
        exploration_sources_by_agent: Dict[Any, List[Dict[str, Any]]] = {}
        # Track search_web intents per agent per round to prevent infinite loops
        _search_web_budget: Dict[str, int] = {}  # agent_id -> remaining searches this round
        MAX_SEARCHES_PER_AGENT_PER_ROUND = 1
        # Thread pool for parallel agent execution
        MAX_PARALLEL_AGENTS = min(len(self.roster), 6)

        for round_num in range(1, num_rounds + 1):
            logger.info("Round %d/%d", round_num, num_rounds)
            round_claims: List[Dict[str, Any]] = []
            round_claims_lock = threading.Lock()

            # Refresh sources list from store to get newly ingested web sources
            self.sources = self.store._load_sources_index(self.simulation_id).get("sources", [])

            # Reset search budget per round
            for agent in self.roster:
                _search_web_budget[str(agent.get("agent_id"))] = MAX_SEARCHES_PER_AGENT_PER_ROUND

            # --- Phase 1 & 2: investigate + propose — run ALL agents concurrently ----
            def _investigate_and_propose(agent: Dict[str, Any]) -> None:
                recall = self._run_investigation_phase(
                    round_num, agent, effective_requirement
                )
                selected_sources = recall.get("selected_sources", [])
                if not selected_sources:
                    return

                claims_needed = max(self._min_claims_per_agent, 1)
                for _ in range(claims_needed):
                    claim = self._run_proposal_phase(
                        round_num, agent, recall, effective_requirement
                    )
                    if isinstance(claim, dict) and claim.get("type") == "search_result":
                        agent_id = str(agent.get("agent_id"))
                        if _search_web_budget.get(agent_id, 0) > 0:
                            _search_web_budget[agent_id] -= 1
                            search_feedback = None
                            if claim.get("ingested_count", 0) == 0:
                                search_feedback = f"Your previous web search for '{claim.get('query')}' yielded 0 new useful sources (either no results or duplicates). Do not search for the exact same query again. You must formulate a claim using existing sources or search for something substantially different."
                            recall = self._run_investigation_phase(
                                round_num, agent, effective_requirement
                            )
                            claim = self._run_proposal_phase(
                                round_num, agent, recall, effective_requirement, search_feedback=search_feedback
                            )

                    if isinstance(claim, dict) and "claim_id" in claim:
                        with round_claims_lock:
                            round_claims.append(claim)

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

            # --- Phase 3: peer review — run all claims concurrently ----
            def _review_claim(claim: Dict[str, Any]) -> None:
                proposer = self._find_agent(claim.get("agent_id"))
                reviewer = self._pick_reviewer(proposer, claim)
                if reviewer is None:
                    logger.warning("No reviewer found for claim %s", claim.get("claim_id"))
                    return
                trial = self._run_peer_review_phase(
                    round_num, claim, proposer, reviewer, effective_requirement
                )

                if isinstance(trial, dict) and trial.get("type") == "search_result":
                    reviewer_id = str(reviewer.get("agent_id"))
                    if _search_web_budget.get(reviewer_id, 0) > 0:
                        _search_web_budget[reviewer_id] -= 1
                        search_feedback = None
                        if trial.get("ingested_count", 0) == 0:
                            search_feedback = f"Your previous web search for '{trial.get('query')}' yielded 0 new useful sources (either no results or duplicates). Do not search for the exact same query again. You must render a verdict ('supports', 'contradicts', or 'needs_revision') based on existing sources."
                        trial = self._run_peer_review_phase(
                            round_num, claim, proposer, reviewer, effective_requirement, search_feedback=search_feedback
                        )

                # --- Phase 4: revision if needed ----
                if isinstance(trial, dict) and trial.get("verdict") == "needs_revision":
                    self._run_revision_phase(
                        round_num, proposer, claim, trial, effective_requirement
                    )

            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as executor:
                futures = {executor.submit(_review_claim, claim): claim for claim in round_claims}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        logger.warning("Peer review failed for a claim: %s", exc)

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

            # Notify caller of round completion
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
                        )
                        discovered = self._ingest_web_results(
                            self.simulation_id, csi_sources, agent, round_num,
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
        selected = self._select_sources(self.sources, query_terms, limit=4)

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
        """Agent proposes a claim via an LLM call. Falls back to template on
        failure."""
        selected_sources = recall.get("selected_sources", [])
        source_snippets = _format_source_snippets(selected_sources)
        source_ids = _dedupe_preserve_order([s.get("source_id") for s in selected_sources])

        messages = _build_propose_messages(agent, source_snippets, simulation_requirement, search_feedback=search_feedback)

        try:
            raw = self.llm.chat(messages=messages, temperature=0.7, max_tokens=1536)
            
            # 0. Check for Native Tool Call wrap from LLMClient (Groq Compound path)
            native_tool_match = re.search(r'<execute_tool>\s*(.*?)\s*</execute_tool>', raw, re.DOTALL)
            if native_tool_match:
                try:
                    native_data = json.loads(native_tool_match.group(1))
                    if native_data.get("name") == "web_search":
                        results = native_data.get("parameters", {}).get("results", [])
                        if results:
                            # Direct ingest from native search
                            csi_sources = []
                            for r in results:
                                csi_sources.append({
                                    "title": r.get("title", "Untitled"),
                                    "url": r.get("url"),
                                    "content": r.get("content", ""),
                                    "score": r.get("score", 0.5),
                                    "source_type": "web"
                                })
                            
                            ingested = self._ingest_web_results(self.simulation_id, csi_sources, agent, round_num)
                            
                            # Record the Native Search action
                            self.store.record_agent_action(self.simulation_id, {
                                "action_type": "NATIVE_SEARCH",
                                "agent_id": agent.get("agent_id"),
                                "agent_name": agent.get("agent_name"),
                                "entity_uuid": agent.get("entity_uuid"),
                                "role": agent.get("role"),
                                "round_num": round_num,
                                "detail": {
                                    "ingested_count": len(ingested),
                                    "intent": "groq_native_compound_search"
                                },
                            })
                            return {"type": "search_result", "ingested_count": len(ingested), "query": "native_groq_search"}
                except Exception as e:
                    logger.warning(f"Failed to parse native tool wrap: {e}")

            # 1. Parse JSON action (Existing path)
            action_data = {}
            for pattern in [r'\{[^{}]*\}', r'\{.*\}']:
                m = re.search(pattern, raw.strip(), re.DOTALL)
                if m:
                    try:
                        action_data = json.loads(m.group(0))
                        break
                    except json.JSONDecodeError:
                        continue
            
            # Intercept search_web or native model tool calls
            # Check for native Groq 'web_search' or LightPanda 'web.run' or browser.search
            is_search = (
                action_data.get("action") == "search_web" or 
                action_data.get("name") in ("web_search", "web.run", "browser.search")
            )
            if is_search:
                # Extract query from action_data['search_query'], ['query'], or ['arguments']['queries'][0]
                query = action_data.get("search_query") or action_data.get("query")
                if not query and "arguments" in action_data:
                    args = action_data.get("arguments", {})
                    query = args.get("search_query") or args.get("query")
                    if not query:
                        queries = args.get("queries", [])
                        if isinstance(queries, list) and len(queries) > 0:
                            query = queries[0]
                        elif isinstance(queries, str):
                            query = queries
                
                if query and self._agent_has_action(agent, "SEARCH_WEB"):
                    web_client = self._get_web_client()
                    if web_client:
                        logger.info("Phase 1 Intent: Agent %s requested search: '%s'", agent.get("agent_name"), query)
                        csi_sources = web_client.search_as_csi_sources(
                            query=query, agent_name=agent.get("agent_name"), round_num=round_num, max_results=3, search_depth="basic"
                        )
                        ingested = self._ingest_web_results(self.simulation_id, csi_sources, agent, round_num)
                        
                        # Refresh local sources and index to ensure THE SAME AGENT sees them immediately
                        # in the next proposal chunk of the SAME ROUND.
                        with self._sources_lock:
                            updated_idx = self.store._load_sources_index(self.simulation_id)
                            self.sources = updated_idx.get("sources", [])
                            # Inject into recall so the agent "knows" what it just found
                            if "selected_sources" in recall:
                                existing_ids = {s.get("source_id") for s in recall["selected_sources"]}
                                for new_s in ingested:
                                    if new_s.get("source_id") not in existing_ids:
                                        recall["selected_sources"].append(new_s)
                        
                        # Record the SEARCH_WEB action
                        self.store.record_agent_action(self.simulation_id, {
                            "action_type": "SEARCH_WEB",
                            "agent_id": agent.get("agent_id"),
                            "agent_name": agent.get("agent_name"),
                            "entity_uuid": agent.get("entity_uuid"),
                            "role": agent.get("role"),
                            "round_num": round_num,
                            "detail": {"query": query, "ingested_count": len(ingested), "intent": "missing_evidence_in_proposal"},
                        })
                        # Return to abort claim creation in this cycle; they will propose next cycle with new data
                        return {"type": "search_result", "ingested_count": len(ingested), "query": query}
            
            claim_text = action_data.get("claim") or _extract_field(raw, "CLAIM") or raw.strip()
            conf_val = action_data.get("confidence")
            confidence = float(conf_val) if conf_val is not None else _extract_confidence(raw)

        except Exception:
            logger.warning(
                "LLM proposal failed for agent %s — falling back to template",
                agent.get("agent_name"),
                exc_info=True,
            )
            raw = self._template_draft_claim(agent, selected_sources, round_num)
            claim_text = _extract_field(raw, "CLAIM") or raw.strip()
            confidence = _extract_confidence(raw)

        claim_text = self._normalize_claim_text(claim_text)
        if not self._is_valid_claim_text(claim_text):
            logger.warning(
                "Discarding malformed claim from %s in round %d",
                agent.get("agent_name"),
                round_num,
            )
            return None

        # Enforce minimum evidence count
        if len(source_ids) < self._require_evidence_count:
            logger.warning(
                "Claim by %s cites %d sources (need %d) — recording anyway",
                agent.get("agent_name"),
                len(source_ids),
                self._require_evidence_count,
            )

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
        """Peer reviews a claim via LLM. Falls back to template heuristic on
        failure."""
        if not self._is_valid_claim_text(claim.get("text", "")):
            logger.warning("Skipping peer review for malformed claim %s", claim.get("claim_id"))
            return None

        # Re-select sources from reviewer's perspective
        query_terms = self._agent_query_terms(reviewer, claim.get("text", ""))
        selected_sources = self._select_sources(self.sources, query_terms, limit=3)
        source_snippets = _format_source_snippets(selected_sources)

        messages = _build_review_messages(
            reviewer, proposer, claim.get("text", ""), source_snippets, search_feedback=search_feedback
        )

        try:
            raw = self.llm.chat(messages=messages, temperature=0.4, max_tokens=1536)
            
            # 0. Check for Native Tool Call wrap from LLMClient (Groq Compound path)
            native_tool_match = re.search(r'<execute_tool>\s*(.*?)\s*</execute_tool>', raw, re.DOTALL)
            if native_tool_match:
                try:
                    native_data = json.loads(native_tool_match.group(1))
                    if native_data.get("name") == "web_search":
                        results = native_data.get("parameters", {}).get("results", [])
                        if results:
                            # Direct ingest from native search
                            csi_sources = []
                            for r in results:
                                csi_sources.append({
                                    "title": r.get("title", "Untitled"),
                                    "url": r.get("url"),
                                    "content": r.get("content", ""),
                                    "score": r.get("score", 0.5),
                                    "source_type": "web"
                                })
                            
                            ingested = self._ingest_web_results(self.simulation_id, csi_sources, reviewer, round_num)
                            
                            # Record the Native Search action
                            self.store.record_agent_action(self.simulation_id, {
                                "action_type": "NATIVE_SEARCH",
                                "agent_id": reviewer.get("agent_id"),
                                "agent_name": reviewer.get("agent_name"),
                                "entity_uuid": reviewer.get("entity_uuid"),
                                "role": reviewer.get("role"),
                                "round_num": round_num,
                                "detail": {
                                    "ingested_count": len(ingested),
                                    "intent": "groq_native_compound_search",
                                    "target_claim": claim.get("claim_id")
                                },
                            })
                            return {"type": "search_result", "ingested_count": len(ingested), "query": "native_groq_search"}
                except Exception as e:
                    logger.warning(f"Failed to parse native tool wrap in review: {e}")

            # 1. Parse JSON action
            action_data = {}
            for pattern in [r'\{[^{}]*\}', r'\{.*\}']:
                m = re.search(pattern, raw.strip(), re.DOTALL)
                if m:
                    try:
                        action_data = json.loads(m.group(0))
                        break
                    except json.JSONDecodeError:
                        continue
            
            # Intercept search_web or native model tool calls
            # Check for native Groq 'web_search' or LightPanda 'web.run'
            is_search = action_data.get("action") == "search_web" or action_data.get("name") in ("web_search", "web.run")
            if is_search:
                # Extract query from action_data['search_query'], ['query'], or ['arguments']['queries'][0]
                query = action_data.get("search_query") or action_data.get("query")
                if not query and "arguments" in action_data:
                    args = action_data.get("arguments", {})
                    query = args.get("search_query") or args.get("query")
                    if not query:
                        queries = args.get("queries", [])
                        if isinstance(queries, list) and len(queries) > 0:
                            query = queries[0]
                        elif isinstance(queries, str):
                            query = queries
                
                if query and self._agent_has_action(reviewer, "SEARCH_WEB"):
                    web_client = self._get_web_client()
                    if web_client:
                        logger.info("Phase 1 Intent: Reviewer %s requested search: '%s'", reviewer.get("agent_name"), query)
                        csi_sources = web_client.search_as_csi_sources(
                            query=query, agent_name=reviewer.get("agent_name"), round_num=round_num, max_results=3, search_depth="basic"
                        )
                        ingested = self._ingest_web_results(self.simulation_id, csi_sources, reviewer, round_num)
                        
                        self.store.record_agent_action(self.simulation_id, {
                            "action_type": "SEARCH_WEB",
                            "agent_id": reviewer.get("agent_id"),
                            "agent_name": reviewer.get("agent_name"),
                            "entity_uuid": reviewer.get("entity_uuid"),
                            "role": reviewer.get("role"),
                            "round_num": round_num,
                            "detail": {"query": query, "ingested_count": len(ingested), "intent": "missing_evidence_in_review", "target_claim": claim.get("claim_id")},
                        })
                        # Return dict to abort peer review in this cycle
                        return {"type": "search_result", "ingested_count": len(ingested), "query": query}
            
            verdict_raw = action_data.get("verdict", _extract_field(raw, "VERDICT")).lower().strip()
            reasoning = action_data.get("reasoning", _extract_field(raw, "REASONING")) or raw.strip()

        except Exception:
            logger.warning(
                "LLM review failed for reviewer %s — falling back to template",
                reviewer.get("agent_name"),
                exc_info=True,
            )
            verdict_raw, reasoning = self._template_peer_response(
                proposer, reviewer, selected_sources, claim.get("text", "")
            )

        # Normalize to valid verdict
        verdict = "needs_revision"
        for valid in _VALID_VERDICTS:
            if valid in verdict_raw:
                verdict = valid
                break

        reasoning = self._normalize_reasoning_text(reasoning or raw.strip())
        if not reasoning:
            verdict, reasoning = self._template_peer_response(
                proposer, reviewer, selected_sources, claim.get("text", "")
            )

        trial_record = self.store.record_trial(self.simulation_id, {
            "trial_kind": "peer_review",
            "round_num": round_num,
            "query_agent_id": proposer.get("agent_id"),
            "query_agent_name": proposer.get("agent_name"),
            "target_agent_id": reviewer.get("agent_id"),
            "target_agent_name": reviewer.get("agent_name"),
            "claim_id": claim.get("claim_id"),
            "query": f"Review claim: {claim.get('text', '')[:200]}",
            "response": reasoning,
            "verdict": verdict,
            "source_ids": _dedupe_preserve_order([s.get("source_id") for s in selected_sources]),
        })

        # Record relation: supports or contradicts
        relation_type = "supports" if verdict == "supports" else "contradicts"
        self.store.record_relation(self.simulation_id, {
            "relation_type": relation_type,
            "from_id": trial_record.get("trial_id"),
            "to_id": claim.get("claim_id"),
            "metadata": {"verdict": verdict, "reviewer": reviewer.get("agent_name")},
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
                "trial_id": trial_record.get("trial_id"),
                "claim_id": claim.get("claim_id"),
                "verdict": verdict,
            },
        })

        with self._trials_lock:
            self._trials.append(trial_record)
        return trial_record

    def _run_revision_phase(
        self,
        round_num: int,
        agent: Dict[str, Any],
        original_claim: Dict[str, Any],
        trial: Dict[str, Any],
        simulation_requirement: str,
    ) -> Optional[Dict[str, Any]]:
        """Agent revises a claim after peer feedback via LLM call."""
        reviewer = self._find_agent(trial.get("target_agent_id"))
        source_ids = original_claim.get("source_ids", [])
        selected_sources = [
            s for s in self.sources if s.get("source_id") in set(source_ids)
        ]
        source_snippets = _format_source_snippets(selected_sources)

        messages = _build_revise_messages(
            agent,
            reviewer,
            original_claim.get("text", ""),
            trial.get("verdict", "needs_revision"),
            trial.get("response", ""),
            source_snippets,
        )

        try:
            raw = self.llm.chat(messages=messages, temperature=0.5, max_tokens=1536)
        except Exception:
            logger.warning(
                "LLM revision failed for agent %s — keeping original claim",
                agent.get("agent_name"),
                exc_info=True,
            )
            return None

        revised_text = self._normalize_claim_text(raw.strip())
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
        """Agent synthesizes multiple related claims into a consolidated
        finding via LLM call."""
        claims_text = "\n".join(
            f"- [{c.get('claim_id', '?')}] (conf={c.get('confidence', '?')}): "
            f"{c.get('text', '')[:300]}"
            for c in related_claims
        )

        messages = _build_synthesis_messages(agent, claims_text, simulation_requirement)

        try:
            # Use low-cost Llama-3.1-8B for logistics synthesis turns
            if "llama-3.1-8b" in Config.LLM_MODEL_NAME.lower() or "instant" in Config.LLM_MODEL_NAME.lower():
                raw = self.llm.chat(messages=messages, temperature=0.5, max_tokens=1536)
            else:
                # If we're on a logic-heavy model, still use it but note the task type
                raw = self.llm.chat(messages=messages, temperature=0.5, max_tokens=1536)
        except Exception as exc:
            if _is_access_denied_llm_error(exc):
                logger.warning(
                    "LLM synthesis unavailable for agent %s due to provider access denial — skipping",
                    agent.get("agent_name"),
                )
            else:
                logger.warning(
                    "LLM synthesis failed for agent %s — skipping",
                    agent.get("agent_name"),
                    exc_info=True,
                )
            return None

        synth_text = self._normalize_claim_text(_extract_field(raw, "CLAIM") or raw.strip())
        if not self._is_valid_claim_text(synth_text):
            logger.warning(
                "Discarding malformed synthesis from %s in round %d",
                agent.get("agent_name"),
                round_num,
            )
            return None
        confidence = _extract_confidence(raw)

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
        """For Deep Research, all agents possess native intent capabilities."""
        return True

    def _generate_search_queries(
        self, agent: Dict[str, Any], simulation_requirement: str, round_num: int,
    ) -> List[str]:
        """LLM generates 2-3 search queries tailored to agent's role."""
        messages = _build_search_query_messages(agent, simulation_requirement, round_num)
        queries: List[str] = []
        try:
            raw = self.llm.chat(messages=messages, temperature=0.7, max_tokens=600)
            
            # Extract JSON object using regex - try multiple patterns
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
            
            # Fallback parse if JSON failed by looking for list items
            if not queries:
                for line in raw.strip().splitlines():
                    clean_line = re.sub(r"^\s*[\d\-\.\)\*\"\'\[\]\,]+\s*", "", line).strip()
                    # skip markdown and intro phrases
                    if len(clean_line) > 10 and not clean_line.lower().startswith((
                        "here", "sure", "i am", "my queries", "queries", 
                        "according", "json", "note", "the user", "knowledge"
                    )):
                        queries.append(clean_line[:120].strip("',\""))

        except Exception as e:
            logger.warning(
                "LLM search-query generation failed for %s — using fallback. Error: %s",
                agent.get("agent_name"), str(e)
            )

        if queries:
            return queries[:3]
            
        # Hard fallback: construct a query from their responsibility to ensure unique paths
        role = agent.get("research_role") or agent.get("role") or "expert"
        goal = agent.get("responsibility") or simulation_requirement
        return [f"{role} {goal} latest news"[:120].strip()]

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
    ) -> List[Dict[str, Any]]:
        """Convert web search results into CSI sources, chunking large texts, add to self.sources, and
        record them in the store's sources index."""
        ingested: List[Dict[str, Any]] = []
        with self._sources_lock:
            existing_ids = {s.get("source_id") for s in self.sources}

        for src in results:
            content = src.get("content", "")
            chunks = TextProcessor.split_text(TextProcessor.preprocess_text(content), chunk_size=850, overlap=120)
            if not chunks and content.strip():
                chunks = [content.strip()]
            
            base_id = src.get("source_id", uuid.uuid4().hex[:12])
            
            for i, chunk in enumerate(chunks):
                sid = f"{base_id}_part{i+1}" if len(chunks) > 1 else base_id
                
                if sid in existing_ids:
                    continue  # deduplicate
                
                chunk_src = src.copy()
                title = f"{src.get('title', 'Unknown Source')} (Part {i+1}/{len(chunks)})" if len(chunks) > 1 else src.get('title', 'Unknown Source')
                chunk_src["source_id"] = sid
                chunk_src["title"] = title
                
                # Apply map-reduce filter: Extract context-rich atomic facts
                atomic = self._extract_atomic_claims(chunk, title)
                if not atomic:
                    atomic = chunk
                
                chunk_src["content"] = chunk
                chunk_src["atomic_claims"] = atomic  # New extracted facts
                
                # Ensure required fields
                chunk_src.setdefault("created_at", "")
                chunk_src.setdefault("updated_at", "")

                with self._sources_lock:
                    if sid in existing_ids:
                        continue  # deduplicate in case another thread added same id
                    self.sources.append(chunk_src)
                    existing_ids.add(sid)
                ingested.append(chunk_src)

        # Persist to the store's sources index
        if ingested:
            try:
                idx = self.store._load_sources_index(simulation_id)
                idx_sources = idx.get("sources", [])
                idx_sources.extend(ingested)
                idx["sources"] = idx_sources
                idx["source_count"] = len(idx_sources)
                self.store._save_sources_index(simulation_id, idx)
            except Exception as exc:
                logger.warning("Failed to persist web sources to index: %s", exc)

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
                csi_sources = web_client.search_as_csi_sources(
                    query=query,
                    agent_name=agent_name,
                    round_num=round_num,
                    max_results=10,
                    search_depth="advanced",
                )

                ingested = self._ingest_web_results(
                    self.simulation_id, csi_sources, agent, round_num,
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
            self.simulation_id, csi_sources, agent, round_num,
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
    ) -> Optional[Dict[str, Any]]:
        """Select a peer reviewer. Prefers agents whose research_role is in
        the proposer's challenge_targets, excluding the proposer themselves."""
        proposer_id = proposer.get("agent_id")
        challenge_targets = proposer.get("challenge_targets", [])

        # Normalize challenge targets for fuzzy matching
        normalized_targets = {
            t.replace("_", "-").lower() for t in challenge_targets
        }

        # First pass: find a reviewer whose research_role is a challenge target
        candidates: List[Dict[str, Any]] = []
        for agent in self.roster:
            if agent.get("agent_id") == proposer_id:
                continue
            role_normalized = (agent.get("research_role") or "").replace("_", "-").lower()
            if role_normalized in normalized_targets:
                candidates.append(agent)

        if candidates:
            # Pick the one who has reviewed the fewest claims so far
            review_counts: Dict[Any, int] = {}
            for t in self._trials:
                tid = t.get("target_agent_id")
                review_counts[tid] = review_counts.get(tid, 0) + 1
            candidates.sort(key=lambda a: review_counts.get(a.get("agent_id"), 0))
            return candidates[0]

        # Fallback: any agent that is not the proposer
        if self._require_opposing_review:
            # Try agents with a different research_role
            proposer_role = (proposer.get("research_role") or "").lower()
            for agent in self.roster:
                if agent.get("agent_id") == proposer_id:
                    continue
                if (agent.get("research_role") or "").lower() != proposer_role:
                    return agent

        # Last resort: anyone else
        for agent in self.roster:
            if agent.get("agent_id") != proposer_id:
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
    ) -> List[Dict[str, Any]]:
        """Select highest-quality sources for investigation, with re-validation."""
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
        ranked = sorted(
            validated_sources,
            key=lambda src: self._score_source(src, query_terms),
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
