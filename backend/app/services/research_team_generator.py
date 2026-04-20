"""
Research Team Generator
Creates balanced research agent teams from a user query using LLM,
without requiring uploaded documents. Designed for web-only research mode.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("mirofish.research_team_generator")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_ROLES: List[str] = [
    "explorer",
    "domain_expert",
    "fact_checker",
    "challenger",
    "synthesizer",
    "communicator",
]

OPTIONAL_ROLES: List[str] = [
    "methodologist",
    "second_domain_expert",
]

# Maps each role to default world_actions and peer_actions
ROLE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "explorer": {
        "world_actions": ["SEARCH_WEB", "READ_URL"],
        "peer_actions": ["PROPOSE_CLAIM", "SHARE_SOURCE"],
        "evidence_priority": "source_diversity",
        "challenge_targets": ["fact_checker"],
    },
    "domain_expert": {
        "world_actions": ["SEARCH_WEB", "READ_URL"],
        "peer_actions": ["PROPOSE_CLAIM", "EVALUATE_CLAIM", "PROVIDE_CONTEXT"],
        "evidence_priority": "technical_correctness",
        "challenge_targets": ["challenger"],
    },
    "fact_checker": {
        "world_actions": ["SEARCH_WEB", "READ_URL"],
        "peer_actions": ["VERIFY_CLAIM", "CHALLENGE_CLAIM", "REQUEST_SOURCE"],
        "evidence_priority": "peer_reviewed",
        "challenge_targets": ["explorer", "domain_expert"],
    },
    "challenger": {
        "world_actions": ["SEARCH_WEB", "READ_URL"],
        "peer_actions": ["CHALLENGE_CLAIM", "COUNTER_ARGUE", "REQUEST_EVIDENCE"],
        "evidence_priority": "counter_evidence",
        "challenge_targets": ["domain_expert", "synthesizer"],
    },
    "synthesizer": {
        "world_actions": ["SEARCH_WEB"],
        "peer_actions": ["SYNTHESIZE", "RESOLVE_CONTRADICTION", "PROPOSE_CONCLUSION"],
        "evidence_priority": "coherence",
        "challenge_targets": ["communicator"],
    },
    "communicator": {
        "world_actions": ["SEARCH_WEB"],
        "peer_actions": ["SUMMARIZE", "TRANSLATE_FINDING", "DRAFT_REPORT"],
        "evidence_priority": "clarity",
        "challenge_targets": [],
    },
    "methodologist": {
        "world_actions": ["SEARCH_WEB", "READ_URL"],
        "peer_actions": ["EVALUATE_METHOD", "PROPOSE_FRAMEWORK", "CHALLENGE_CLAIM"],
        "evidence_priority": "methodological_rigor",
        "challenge_targets": ["domain_expert", "explorer"],
    },
    "second_domain_expert": {
        "world_actions": ["SEARCH_WEB", "READ_URL"],
        "peer_actions": ["PROPOSE_CLAIM", "EVALUATE_CLAIM", "COUNTER_ARGUE"],
        "evidence_priority": "technical_correctness",
        "challenge_targets": ["domain_expert", "challenger"],
    },
}

_HEALTH_ROLE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "medical_researcher": {
        "world_actions": ["SEARCH_WEB"],
        "peer_actions": ["PROPOSE_CLAIM", "VERIFY_CLAIM"],
        "evidence_priority": "clinical_evidence",
        "challenge_targets": ["primary_physician"],
    },
    "primary_physician": {
        "world_actions": ["SEARCH_WEB"],
        "peer_actions": ["PROPOSE_CLAIM", "CHALLENGE_CLAIM"],
        "evidence_priority": "diagnostic_accuracy",
        "challenge_targets": ["diagnostician", "medical_researcher"],
    },
    "clinical_pharmacologist": {
        "world_actions": ["SEARCH_WEB"],
        "peer_actions": ["CHALLENGE_CLAIM", "VERIFY_CLAIM"],
        "evidence_priority": "pharmacological_safety",
        "challenge_targets": ["primary_physician", "diagnostician"],
    },
    "diagnostician": {
        "world_actions": ["SEARCH_WEB"],
        "peer_actions": ["PROPOSE_CLAIM", "CHALLENGE_CLAIM"],
        "evidence_priority": "diagnostic_accuracy",
        "challenge_targets": ["medical_researcher", "primary_physician"],
    },
    "medical_synthesizer": {
        "world_actions": [],
        "peer_actions": ["SYNTHESIZE"],
        "evidence_priority": "clinical_consensus",
        "challenge_targets": [],
    },
    "patient_advocate": {
        "world_actions": [],
        "peer_actions": ["CHALLENGE_CLAIM", "VERIFY_CLAIM"],
        "evidence_priority": "patient_safety",
        "challenge_targets": ["primary_physician", "diagnostician", "clinical_pharmacologist"],
    },
}

HEALTH_REQUIRED_ROLES: List[str] = list(_HEALTH_ROLE_DEFAULTS.keys())


# ---------------------------------------------------------------------------
# Dataclass for agent output
# ---------------------------------------------------------------------------

@dataclass
class ResearchAgent:
    """Single research agent generated from a query."""
    agent_id: int
    agent_name: str
    entity_name: str
    entity_type: str
    bio: str
    persona: str
    research_role: str
    responsibility: str
    evidence_priority: str
    world_actions: List[str] = field(default_factory=list)
    peer_actions: List[str] = field(default_factory=list)
    challenge_targets: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    qualification_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Ensure 'role' is present as a mirror of 'research_role' for CSI compatibility
        d["role"] = self.research_role
        return d


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_TEAM_GENERATION_PROMPT = """\
You are a research team architect. Given a research query, you must design \
a team of {team_size} research agents that collectively cover ALL 6 required \
competencies and can investigate the query rigorously.

## Research Query
{query}

## Required Competencies (every team MUST have at least 1 agent per role)

1. **explorer** — Discovers primary and secondary sources via web search. \
   world_actions: ["SEARCH_WEB", "READ_URL"]
2. **domain_expert** — Deep technical/domain knowledge relevant to the query. \
   world_actions: ["SEARCH_WEB", "READ_URL"]
3. **fact_checker** — Verifies claims against independent, authoritative sources. \
   world_actions: ["SEARCH_WEB", "READ_URL"]
4. **challenger** — Adversarial reviewer who seeks counter-evidence and weaknesses. \
   world_actions: ["SEARCH_WEB", "READ_URL"]
5. **synthesizer** — Combines findings, resolves contradictions, builds coherent picture. \
   world_actions: ["SEARCH_WEB"]
6. **communicator** — Translates findings for the intended audience. \
   world_actions: ["SEARCH_WEB"]

## Optional Roles (use if team_size > 6)

- **methodologist** — Evaluates research methods and frameworks. \
  world_actions: ["SEARCH_WEB", "READ_URL"]
- **second_domain_expert** — Provides an alternative domain perspective. \
  world_actions: ["SEARCH_WEB", "READ_URL"]

## Team Design Rules

1. Every required role must be assigned to at least 1 agent.
2. At least 2 agents must have SEARCH_WEB in their world_actions.
3. At least 2 agents must hold genuinely **opposing perspectives** on the query \
   (built-in intellectual tension — identify which agents oppose each other).
4. Each agent gets a realistic name, a 2-3 sentence bio, and a detailed persona.
5. Assign a `qualification_score` (0.0-1.0) reflecting how well each agent \
   matches their role for THIS specific query.
6. Assign domain-specific `skills` (3-5 per agent).
7. The `responsibility` field must be specific to THIS query — not generic.

## Output Format — strict JSON

Return a JSON object with exactly this schema:
{{
  "agents": [
    {{
      "agent_id": <int starting from 1>,
      "agent_name": "<full realistic name>",
      "entity_name": "<same as agent_name>",
      "entity_type": "<professional title, e.g. 'AI Researcher'>",
      "bio": "<2-3 sentence bio>",
      "persona": "<detailed persona: background, beliefs, communication style, biases>",
      "research_role": "<one of the 6 required or 2 optional roles>",
      "responsibility": "<specific responsibility for THIS query>",
      "evidence_priority": "<e.g. technical_correctness, market_data, peer_reviewed, counter_evidence, source_diversity, clarity, coherence, methodological_rigor>",
      "world_actions": ["SEARCH_WEB", "READ_URL"],
      "peer_actions": ["PROPOSE_CLAIM", "CHALLENGE_CLAIM"],
      "challenge_targets": ["<roles this agent challenges>"],
      "skills": ["skill1", "skill2", "skill3"],
      "qualification_score": 0.85
    }}
  ],
  "opposing_pairs": [
    {{
      "agent_a_id": 2,
      "agent_b_id": 4,
      "tension_description": "<what they disagree on>"
    }}
  ]
}}

Generate exactly {team_size} agents. Return ONLY valid JSON — no markdown fences, \
no commentary.
"""

_HEALTH_TEAM_GENERATION_PROMPT = """\
You are a clinical team architect. Given a patient health query, you must compose \
a team of {team_size} medical agents that collectively cover ALL 6 required clinical \
roles and can investigate the query with rigorous evidence-based medicine (EBM).

## Patient / Health Query
{query}

## Required Clinical Roles (every team MUST include exactly 1 agent per role)

1. **medical_researcher** — Searches clinical literature, systematic reviews, and \
   RCT databases. world_actions: ["SEARCH_WEB"]
2. **primary_physician** — Provides front-line clinical assessment and diagnosis. \
   world_actions: ["SEARCH_WEB"]
3. **clinical_pharmacologist** — Evaluates drug safety, interactions, and dosing. \
   world_actions: ["SEARCH_WEB"]
4. **diagnostician** — Specialises in differential diagnosis and test interpretation. \
   world_actions: ["SEARCH_WEB"]
5. **medical_synthesizer** — Integrates findings into a coherent clinical picture. \
   world_actions: []
6. **patient_advocate** — Challenges recommendations from a patient-safety and \
   informed-consent perspective. world_actions: []

## Dynamic Specialist Rules (add 1-3 specialists based on query keywords)

Scan the patient query for these signals and add the corresponding specialist:
- cardiovascular / heart / blood pressure / arrhythmia → **cardiologist**
- neurological / brain / seizure / stroke / headache → **neurologist**
- respiratory / lung / asthma / COPD / breathing → **pulmonologist**
- metabolic / diabetes / thyroid / obesity / insulin → **endocrinologist**
- gastrointestinal / liver / bowel / gut / digestion → **gastroenterologist**
- musculoskeletal / joint / bone / arthritis / spine → **rheumatologist**
- mental health / anxiety / depression / psychiatric → **psychiatrist**
- kidney / renal / dialysis / nephrology → **nephrologist**
- oncology / cancer / tumour / chemotherapy → **oncologist**
- paediatric / child / infant / neonatal → **paediatric_specialist**

If no keyword matches, add 1 general **clinical_consultant** to fill the team to \
the required {team_size}.

## EBM Evidence Level — MANDATORY on every claim

Every agent's `evidence_priority` field MUST include an EBM level suffix:
- **_A**: supported by systematic reviews or RCTs
- **_B**: supported by cohort or case-control studies
- **_C**: expert opinion, case reports, or consensus only

Example values: "diagnostic_accuracy_A", "pharmacological_safety_B", \
"clinical_consensus_C"

## Team Design Rules

1. All 6 required clinical roles must be filled before adding specialists.
2. At least 4 agents must hold `"SEARCH_WEB"` in their world_actions.
3. At least 2 opposing_pairs must be identified (clinical tension between roles).
4. Each agent gets a realistic name, 2-3 sentence bio, and a detailed clinical \
   persona including board certifications or specialisation details.
5. Assign a `qualification_score` (0.0-1.0) reflecting expertise fit for THIS query.
6. Assign domain-specific `skills` (3-5 per agent, medical terminology preferred).
7. The `responsibility` field must be specific to THIS health query.

## Output Format — strict JSON

Return a JSON object with exactly this schema:
{{
  "agents": [
    {{
      "agent_id": <int starting from 1>,
      "agent_name": "<full realistic name, e.g. 'Dr. Sarah Chen'>",
      "entity_name": "<same as agent_name>",
      "entity_type": "<professional title, e.g. 'Board-Certified Cardiologist'>",
      "bio": "<2-3 sentence clinical bio>",
      "persona": "<detailed persona: specialisation, clinical philosophy, \
communication style, known biases>",
      "research_role": "<one of the 6 required roles or a dynamic specialist>",
      "responsibility": "<specific clinical responsibility for THIS query>",
      "evidence_priority": "<e.g. clinical_evidence_A, diagnostic_accuracy_B, \
pharmacological_safety_A, patient_safety_C>",
      "world_actions": ["SEARCH_WEB"],
      "peer_actions": ["PROPOSE_CLAIM", "CHALLENGE_CLAIM"],
      "challenge_targets": ["<roles this agent challenges>"],
      "skills": ["skill1", "skill2", "skill3"],
      "qualification_score": 0.90
    }}
  ],
  "opposing_pairs": [
    {{
      "agent_a_id": 1,
      "agent_b_id": 3,
      "tension_description": "<clinical disagreement, e.g. conservative vs \
aggressive treatment approach>"
    }}
  ]
}}

Generate exactly {team_size} agents. Return ONLY valid JSON — no markdown fences, \
no commentary.
"""


# ---------------------------------------------------------------------------
# Generator class
# ---------------------------------------------------------------------------

class ResearchTeamGenerator:
    """Generate a balanced research team from a user query via LLM."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm: LLMClient = llm_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_team(
        self,
        query: str,
        team_size: int = 8,
        mode: str = 'web_research',
    ) -> Dict[str, Any]:
        """Generate a complete research team from a query.

        Args:
            query: The research question or topic.
            team_size: Number of agents (minimum 6, clamped).
            mode: Team generation mode — 'web_research' (default) or 'health'.
                  In 'health' mode a clinical medical team is assembled using
                  _HEALTH_TEAM_GENERATION_PROMPT and _HEALTH_ROLE_DEFAULTS.

        Returns:
            Dictionary with keys:
                - agents: list of agent dicts
                - research_workflow_config: ResearchWorkflowConfig-compatible dict
                - team_competency_coverage: mapping of role -> agent_ids
        """
        is_health = mode == 'health'
        min_size = len(HEALTH_REQUIRED_ROLES) if is_health else len(REQUIRED_ROLES)
        team_size = max(team_size, min_size)
        logger.info(
            "Generating research team for query (size=%d, mode=%s): %.120s",
            team_size,
            mode,
            query,
        )

        raw_team = self._call_llm_for_team(query, team_size, is_health=is_health)
        agents = self._parse_agents(raw_team)
        agents = self._validate_and_patch(agents, query, team_size, is_health=is_health)

        coverage = self._compute_coverage(agents)
        workflow_config = self._build_workflow_config(query, agents)

        logger.info(
            "Research team generated: %d agents, roles covered: %s",
            len(agents),
            list(coverage.keys()),
        )

        return {
            "agents": [a.to_dict() for a in agents],
            "research_workflow_config": workflow_config,
            "team_competency_coverage": coverage,
        }

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    def _call_llm_for_team(
        self,
        query: str,
        team_size: int,
        is_health: bool = False,
    ) -> Dict[str, Any]:
        """Send the team-generation prompt to the LLM and return parsed JSON."""
        template = _HEALTH_TEAM_GENERATION_PROMPT if is_health else _TEAM_GENERATION_PROMPT
        prompt = template.format(query=query, team_size=team_size)
        messages: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are an expert research team designer. "
                    "You output strictly valid JSON with no extra text."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        from ..utils.llm_client import json as _json
        import re as _re

        def _repair_json(text: str) -> str:
            """Fix common LLM JSON errors before parsing."""
            # Remove trailing commas before } or ]
            text = _re.sub(r',\s*([}\]])', r'\1', text)
            # Remove JS-style // comments
            text = _re.sub(r'//[^\n]*', '', text)
            # Close unclosed brackets/braces (best-effort)
            opens = text.count('{') - text.count('}')
            closes = text.count('[') - text.count(']')
            if opens > 0:
                text += '}' * opens
            if closes > 0:
                text += ']' * closes
            return text

        def _try_parse(raw_text: str) -> Dict[str, Any]:
            cleaned = raw_text.strip()
            cleaned = _re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=_re.IGNORECASE)
            cleaned = _re.sub(r'\n?```\s*$', '', cleaned)
            match = _re.search(r'\{[\s\S]*\}', cleaned)
            blob = match.group(0) if match else cleaned
            try:
                return _json.loads(blob)
            except (_json.JSONDecodeError, ValueError):
                repaired = _repair_json(blob)
                return _json.loads(repaired)

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(3):
            try:
                raw_text = self.llm.chat(
                    messages=messages,
                    temperature=0.4 + attempt * 0.1,
                    max_tokens=6144,
                )
                return _try_parse(raw_text)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "LLM team generation attempt %d/3 failed: %s", attempt + 1, exc
                )

        logger.error("LLM call for team generation failed after 3 attempts")
        raise last_exc

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_agents(self, raw: Dict[str, Any]) -> List[ResearchAgent]:
        """Convert raw LLM JSON into a list of ResearchAgent dataclasses."""
        raw_agents: List[Dict[str, Any]] = raw.get("agents", [])
        agents: List[ResearchAgent] = []

        for idx, entry in enumerate(raw_agents):
            try:
                agent = ResearchAgent(
                    agent_id=entry.get("agent_id", idx + 1),
                    agent_name=entry.get("agent_name", f"Agent {idx + 1}"),
                    entity_name=entry.get("entity_name", entry.get("agent_name", f"Agent {idx + 1}")),
                    entity_type=entry.get("entity_type", "Researcher"),
                    bio=entry.get("bio", ""),
                    persona=entry.get("persona", ""),
                    research_role=entry.get("research_role", ""),
                    responsibility=entry.get("responsibility", ""),
                    evidence_priority=entry.get("evidence_priority", ""),
                    world_actions=entry.get("world_actions", []),
                    peer_actions=entry.get("peer_actions", []),
                    challenge_targets=entry.get("challenge_targets", []),
                    skills=entry.get("skills", []),
                    qualification_score=float(entry.get("qualification_score", 0.5)),
                )
                agents.append(agent)
            except (TypeError, ValueError):
                logger.warning("Skipping malformed agent entry at index %d", idx)

        return agents

    # ------------------------------------------------------------------
    # Validation & patching
    # ------------------------------------------------------------------

    def _validate_and_patch(
        self,
        agents: List[ResearchAgent],
        query: str,
        team_size: int,
        is_health: bool = False,
    ) -> List[ResearchAgent]:
        """Ensure all required roles are covered; patch with defaults if not."""
        # --- Deduplication logic to prevent multiplied agent counts ---
        seen_names = set()
        unique_agents = []
        for a in agents:
            name_key = a.agent_name.strip().lower()
            if name_key not in seen_names:
                seen_names.add(name_key)
                unique_agents.append(a)

        if len(unique_agents) < len(agents):
            logger.info("Removed %d duplicate agents from team", len(agents) - len(unique_agents))
            agents = unique_agents

        required_roles = HEALTH_REQUIRED_ROLES if is_health else REQUIRED_ROLES
        role_defaults = _HEALTH_ROLE_DEFAULTS if is_health else ROLE_DEFAULTS

        covered_roles = {a.research_role for a in agents}
        missing_roles = [r for r in required_roles if r not in covered_roles]

        if missing_roles:
            logger.warning(
                "LLM team missing required roles %s — adding defaults", missing_roles
            )
            next_id = max((a.agent_id for a in agents), default=0) + 1
            for role in missing_roles:
                agents.append(self._make_default_agent(next_id, role, query, role_defaults=role_defaults))
                next_id += 1

        # Ensure at least 2 agents have SEARCH_WEB
        search_agents = [a for a in agents if "SEARCH_WEB" in a.world_actions]
        if len(search_agents) < 2:
            web_roles = (
                ("medical_researcher", "primary_physician", "diagnostician")
                if is_health
                else ("explorer", "fact_checker", "challenger")
            )
            patched = 0
            for agent in agents:
                if "SEARCH_WEB" not in agent.world_actions and agent.research_role in web_roles:
                    agent.world_actions = list(set(agent.world_actions) | {"SEARCH_WEB"})
                    patched += 1
                    if len(search_agents) + patched >= 2:
                        break
            if len(search_agents) + patched < 2:
                logger.warning(
                    "Could not ensure 2 SEARCH_WEB agents after patching"
                )

        if is_health:
            # Ensure at least 1 patient_advocate for health mode
            advocates = [a for a in agents if a.research_role == "patient_advocate"]
            if not advocates:
                logger.warning("No patient_advocate found — adding default")
                next_id = max((a.agent_id for a in agents), default=0) + 1
                agents.append(self._make_default_agent(next_id, "patient_advocate", query, role_defaults=role_defaults))
        else:
            # Ensure at least 1 challenger for web_research mode
            challengers = [a for a in agents if a.research_role == "challenger"]
            if not challengers:
                logger.warning("No challenger found — adding default challenger")
                next_id = max((a.agent_id for a in agents), default=0) + 1
                agents.append(self._make_default_agent(next_id, "challenger", query))

        # Re-number agent_ids sequentially
        for idx, agent in enumerate(agents):
            agent.agent_id = idx + 1

        return agents

    def _make_default_agent(
        self,
        agent_id: int,
        role: str,
        query: str,
        role_defaults: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ResearchAgent:
        """Create a fallback agent for a missing role."""
        lookup = role_defaults if role_defaults is not None else ROLE_DEFAULTS
        fallback_key = next(iter(lookup))  # first key as generic fallback
        defaults = lookup.get(role, lookup.get(fallback_key, ROLE_DEFAULTS["explorer"]))
        role_label = role.replace("_", " ").title()

        return ResearchAgent(
            agent_id=agent_id,
            agent_name=f"Default {role_label}",
            entity_name=f"Default {role_label}",
            entity_type=role_label,
            bio=f"Automatically assigned {role_label} for the research query.",
            persona=(
                f"A meticulous {role_label.lower()} who approaches "
                f"research with rigor. Focuses on {defaults['evidence_priority']}."
            ),
            research_role=role,
            responsibility=f"Cover the {role} competency for: {query[:200]}",
            evidence_priority=defaults["evidence_priority"],
            world_actions=list(defaults["world_actions"]),
            peer_actions=list(defaults["peer_actions"]),
            challenge_targets=list(defaults["challenge_targets"]),
            skills=[f"{role}_analysis", "critical_thinking", "evidence_evaluation"],
            qualification_score=0.5,
        )

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_coverage(agents: List[ResearchAgent]) -> Dict[str, List[int]]:
        """Return a mapping of role -> list of agent_ids covering that role."""
        coverage: Dict[str, List[int]] = {}
        for agent in agents:
            coverage.setdefault(agent.research_role, []).append(agent.agent_id)
        return coverage

    # ------------------------------------------------------------------
    # Workflow config builder
    # ------------------------------------------------------------------

    def _build_workflow_config(
        self,
        query: str,
        agents: List[ResearchAgent],
    ) -> Dict[str, Any]:
        """Build a ResearchWorkflowConfig-compatible dict for web research."""
        role_names = sorted({a.research_role for a in agents})

        agent_assignments: List[Dict[str, Any]] = []
        for agent in agents:
            output_types: List[str] = ["extract", "claim"]
            if agent.research_role in ("challenger", "fact_checker"):
                output_types.extend(["support", "contradict"])
            if agent.research_role == "synthesizer":
                output_types.append("verdict")
            if agent.research_role == "communicator":
                output_types.append("report_draft")

            agent_assignments.append({
                "agent_id": agent.agent_id,
                "entity_uuid": f"web-research-{agent.agent_id}",
                "entity_name": agent.entity_name,
                "entity_type": agent.entity_type,
                "research_role": agent.research_role,
                "responsibility": agent.responsibility,
                "evidence_priority": agent.evidence_priority,
                "challenge_targets": agent.challenge_targets,
                "output_types": output_types,
            })

        rounds: List[Dict[str, Any]] = [
            {
                "round_id": "exploration",
                "label": "Web Exploration",
                "description": (
                    "Agents search the web for sources, extract key claims, "
                    "and share initial findings."
                ),
                "expected_outputs": ["extract", "claim", "source_url"],
            },
            {
                "round_id": "analysis",
                "label": "Deep Analysis",
                "description": (
                    "Domain experts and fact-checkers read sources in depth, "
                    "evaluate evidence quality, and verify claims."
                ),
                "expected_outputs": ["evaluation", "verification", "claim"],
            },
            {
                "round_id": "debate",
                "label": "Debate and Challenge",
                "description": (
                    "Challengers present counter-evidence, agents defend or "
                    "revise claims through structured debate."
                ),
                "expected_outputs": ["support", "contradict", "revision"],
            },
            {
                "round_id": "synthesis",
                "label": "Synthesis and Resolution",
                "description": (
                    "Synthesizer combines findings, resolves contradictions, "
                    "and builds a coherent knowledge picture."
                ),
                "expected_outputs": ["verdict", "confidence_score", "synthesis"],
            },
            {
                "round_id": "gate_check",
                "label": "Gate Check and Report",
                "description": (
                    "Verify provenance completeness, check source coverage, "
                    "and produce the final research report."
                ),
                "expected_outputs": ["provenance_path", "gate_status", "report_draft"],
            },
        ]

        is_detailed = "detailed" in query.lower()

        return {
            "workflow_type": "web_research",
            "mode_label": "Web Research / CSI",
            "research_rounds": rounds,
            "agent_assignments": agent_assignments,
            "claim_policy": {
                "require_source_link": True,
                "min_claims_per_agent": 1,
                "allow_web_sources": True,
                "topic_focus": query[:500],
            },
            "debate_policy": {
                "require_opposing_review": True,
                "max_unreviewed_claim_ratio": 0.15,
                "targeted_counterparty_roles": role_names,
            },
            "verdict_policy": {
                "confidence_scale": "low_medium_high",
                "require_evidence_count": 2 if is_detailed else 1,
                "allow_unresolved_contradictions": True,
            },
            "gate_policy": {
                "require_resume_before_final_report": True,
                "minimum_source_coverage": 5,
                "minimum_reviewed_claim_ratio": 0.8,
                "block_on_missing_provenance": True,
            },
        }
