import json
import logging
import uuid
from typing import Dict, Any, List, Optional, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import re
import time

from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..utils.token_usage_tracker import TokenUsageTracker

logger = get_logger("mirofish.agent_harness")

class ActionType(str, Enum):
    SEARCH_WEB = "SEARCH_WEB"
    READ_URL = "READ_URL"
    PROPOSE_CLAIM = "PROPOSE_CLAIM"
    CHALLENGE_CLAIM = "CHALLENGE_CLAIM"
    VERIFY_CLAIM = "VERIFY_CLAIM"
    RECALL = "RECALL"
    SYNTHESIZE = "SYNTHESIZE"
    RESOLVE_CONTRADICTION = "RESOLVE_CONTRADICTION"
    DRAFT_REPORT = "DRAFT_REPORT"
    REVISE_CLAIM = "REVISE_CLAIM"

@dataclass
class ActionBudget:
    max_tokens_per_simulation: int = 5000000
    max_tokens_per_round: int = 1000000
    max_search_queries_per_agent_round: int = 3
    current_tokens_sim: int = 0
    current_tokens_round: int = 0

@dataclass
class ActionResult:
    action_type: ActionType
    agent_id: str
    status: str  # "success", "failed", "budget_exceeded"
    payload: Dict[str, Any] = field(default_factory=dict)
    tokens: Dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0, "total": 0})
    error: Optional[str] = None
    model_used: Optional[str] = None
    
    # For backward compatibility with CSIResearchEngine
    @property
    def success(self) -> bool:
        return self.status == "success"
    
    @property
    def is_search(self) -> bool:
        return self.payload.get("type") == "search_result"
    
    @property
    def search_results(self) -> List[Dict[str, Any]]:
        return self.payload.get("search_results", self.payload.get("sources", []))
    
    @property
    def search_query(self) -> str:
        return self.payload.get("query", "")
    
    @property
    def data(self) -> Dict[str, Any]:
        return self.payload.get("data", self.payload.get("extracted", {}))
    
    @property
    def raw(self) -> str:
        return self.payload.get("raw", self.payload.get("text", ""))
    
    @property
    def trace_id(self) -> str:
        return self.payload.get("trace_id", str(uuid.uuid4()))

class AgentHarness:
    """
    Unified agent action execution layer.
    Enforces policies, task-backed execution, and role contracts.
    """

    def __init__(
        self,
        simulation_id: str,
        policy: Any, # CSIPolicy
        store: Any,
        web_client: Optional[Any] = None,
        llm_client: Optional[LLMClient] = None,
        config_mode: str = "web_research"
    ):
        self.simulation_id = simulation_id
        self.policy = policy
        self.store = store
        self.web_client = web_client
        self.llm = llm_client
        self.config_mode = config_mode
        self.budget_usage = {} # agent_id -> {search_count, token_count}

    def execute(self, *args, **kwargs) -> ActionResult:
        """Execute either the new task-backed call shape or the legacy engine call shape."""
        legacy_mode = "agent" in kwargs or "payload" in kwargs

        if legacy_mode:
            agent = kwargs.get("agent") or {}
            action_type = kwargs.get("action_type", ActionType.PROPOSE_CLAIM)
            payload = dict(kwargs.get("payload") or {})
            round_num = int(kwargs.get("round_num", 0) or 0)
            agent_id = str(agent.get("agent_id") or "agent_0")
            task = {"status": "running", **payload}
        else:
            agent_id = str(args[0]) if len(args) > 0 else str(kwargs.get("agent_id") or "agent_0")
            action_type = args[1] if len(args) > 1 else kwargs.get("action_type", ActionType.PROPOSE_CLAIM)
            task = dict(args[2]) if len(args) > 2 and isinstance(args[2], dict) else dict(kwargs.get("task") or {})
            round_num = int(args[3]) if len(args) > 3 else int(kwargs.get("round_num", 0) or 0)
            agent = dict(task.get("agent") or {})
            agent.setdefault("agent_id", agent_id)

        normalized_action = self._normalize_action_name(action_type)
        result_type = self._coerce_action_type(action_type)

        role_contract = self._resolve_role_contract(agent, normalized_action)
        if role_contract and normalized_action not in role_contract.allowed_actions:
            return ActionResult(
                result_type,
                agent_id,
                "failed",
                error=f"Action {normalized_action} not allowed for role {role_contract.role_id}",
            )

        if not legacy_mode and (not task or task.get("status") != "running"):
            return ActionResult(
                result_type,
                agent_id,
                "failed",
                error="Execution attempt without running task",
            )

        if normalized_action in {"SEARCH_EVIDENCE", "SEARCH_WEB"}:
            usage = self.budget_usage.get(agent_id, {"search_count": 0})
            if self.policy and usage["search_count"] >= self.policy.search.max_search_per_task:
                return ActionResult(result_type, agent_id, "failed", error="Search limit exceeded for task")
            usage["search_count"] += 1
            self.budget_usage[agent_id] = usage

        try:
            return self._dispatch(agent, normalized_action, task, round_num)
        except Exception as e:
            logger.exception(f"Harness execution failed: {e}")
            return ActionResult(result_type, agent_id, "failed", error=str(e))

    def _dispatch(self, agent: Dict[str, Any], action_type: str, task: Dict[str, Any], round_num: int) -> ActionResult:
        """Dispatches to actual tool handlers with result validation."""
        agent_data = {"agent_id": str(agent.get("agent_id") or "agent_0"), **agent}
        model = "gpt-4o" # default

        # 1. Dispatch
        if action_type in {"SEARCH_EVIDENCE", "SEARCH_WEB"}:
            # Pass to health-aware search if in health mode
            result = self._handle_search_web(agent_data, task, round_num, model)
        else:
            # Carry action type into the payload so downstream parsing can be action-aware.
            enriched = dict(task or {})
            enriched.setdefault("action_type", action_type)
            result = self._handle_reasoning_action(agent_data, enriched, round_num, model)

        # 2. VALIDATE RESULTS (Health Providence Enforcement)
        if result.success and self.policy and self.policy.mode == "health":
            if action_type == "SEARCH_EVIDENCE" :
                # Filter results by allowed domains
                allowed = set(self.policy.provenance.allowed_domains)
                raw_results = result.payload.get("search_results", [])
                filtered = [
                    res for res in raw_results 
                    if any(domain in res.get("url", "") for domain in allowed)
                ]
                
                if not filtered and raw_results:
                    result.status = "failed"
                    result.error = "All search results violated clinical domain policy."
                else:
                    result.payload["search_results"] = filtered
                    
        return result

    @staticmethod
    def _normalize_action_name(action_type: Union[str, ActionType]) -> str:
        if isinstance(action_type, ActionType):
            return action_type.value
        return str(action_type or "").upper()

    @staticmethod
    def _coerce_action_type(action_type: Union[str, ActionType]) -> ActionType:
        if isinstance(action_type, ActionType):
            return action_type
        normalized = str(action_type or "").upper()
        if normalized in ActionType.__members__:
            return ActionType[normalized]
        for member in ActionType:
            if member.value == normalized:
                return member
        return ActionType.PROPOSE_CLAIM

    def _resolve_role_contract(self, agent: Dict[str, Any], action_type: str):
        if not self.policy:
            return None

        policy_roles = self.policy.roles or {}
        candidate_keys = []
        for raw_value in (
            agent.get("research_role"),
            agent.get("role"),
            agent.get("profession"),
        ):
            value = str(raw_value or "").strip().lower().replace(" ", "_").replace("-", "_")
            if value:
                candidate_keys.append(value)

        for key in candidate_keys:
            if key in policy_roles:
                return policy_roles[key]

        for contract in policy_roles.values():
            if action_type in contract.allowed_actions:
                return contract

        return None

    def _get_handler(self, action_type: ActionType) -> Callable:
        handlers = {
            ActionType.SEARCH_WEB: self._handle_search_web,
            ActionType.PROPOSE_CLAIM: self._handle_reasoning_action,
            ActionType.CHALLENGE_CLAIM: self._handle_reasoning_action,
            ActionType.VERIFY_CLAIM: self._handle_reasoning_action,
            ActionType.RECALL: self._handle_reasoning_action,
            ActionType.SYNTHESIZE: self._handle_reasoning_action,
            ActionType.REVISE_CLAIM: self._handle_reasoning_action,
        }
        return handlers.get(action_type, self._handle_reasoning_action)

    def _handle_search_web(self, agent: Dict[str, Any], payload: Dict[str, Any], round_num: int, model: str) -> ActionResult:
        query = payload.get("query")
        if not query:
            return ActionResult(ActionType.SEARCH_WEB, str(agent.get("agent_id")), "failed", error="Empty search query")

        if not self.web_client:
            return ActionResult(ActionType.SEARCH_WEB, str(agent.get("agent_id")), "failed", error="Web client not available")

        # Apply medical source routing for health mode
        if self.config_mode == 'health':
            query = f"clinical evidence {query}"
            search_depth = "advanced"
        else:
            search_depth = "basic"

        # Primary: Groq Compound (Native reasoning search)
        try:
            csi_sources = self.web_client.search_as_csi_sources(
                query=query,
                agent_name=agent.get("agent_name"),
                round_num=round_num,
                max_results=3,
                search_depth=search_depth,
                provider_mode="groq_only",
            )

            # Fallback logic remained consistent with requirement
            if not csi_sources and self.web_client.is_tavily_available():
                csi_sources = self.web_client.search_as_csi_sources(
                    query=query,
                    agent_name=agent.get("agent_name"),
                    round_num=round_num,
                    max_results=3,
                    search_depth="advanced",
                    provider_mode="tavily_only",
                )

            return ActionResult(
                ActionType.SEARCH_WEB,
                str(agent.get("agent_id")),
                "success",
                payload={"sources": csi_sources, "query": query},
                model_used=model
            )
        except Exception as e:
            return ActionResult(ActionType.SEARCH_WEB, str(agent.get("agent_id")), "failed", error=str(e))

    def _handle_reasoning_action(self, agent: Dict[str, Any], payload: Dict[str, Any], round_num: int, model: str) -> ActionResult:
        """Generic handler for reasoning-based actions using GPT-OSS-20B."""
        messages = payload.get("messages")
        if not messages:
            return ActionResult(ActionType.SYNTHESIZE, str(agent.get("agent_id")), "failed", error=f"No messages provided for {payload.get('action_type')}")

        try:
            # We use text-based output to avoid provider-side 400 validation errors.
            response_text = self.llm.chat(
                messages=messages,
                temperature=payload.get("temperature", 0.4),
                max_tokens=payload.get("max_tokens", 4096)
            )
            
            # Record tokens using the tracker (which should be updated by llm.chat)
            tokens = {"prompt": 0, "completion": 0, "total": 0}
            
            # Extraction logic (action-aware best-effort parse).
            extracted_data = self._parse_response(
                response_text,
                action_type=str(payload.get("action_type") or ""),
            )
            
            # Handle SEARCH_WEB intent even when the provider returns a rejected tool-call payload.
            upper_response = response_text.upper()
            intent_to_search = any(
                marker in upper_response
                for marker in ["SEARCH_WEB", "<EXECUTE_TOOL>", '"NAME": "WEB.RUN"', '"NAME": "WEB_SEARCH"', '"ACTION":"SEARCH_WEB"']
            )
            if intent_to_search:
                extracted_query = self._extract_search_query(response_text, extracted_data)
                if extracted_query:
                    # Return a special search_result status so the engine knows to refresh
                    return ActionResult(
                        ActionType.SEARCH_WEB,
                        str(agent.get("agent_id")),
                        "success",
                        payload={"type": "search_result", "query": extracted_query, "text": response_text, "search_results": []},
                        tokens=tokens,
                        model_used=model
                    )
            
            return ActionResult(
                payload.get("action_type", ActionType.PROPOSE_CLAIM),
                str(agent.get("agent_id")),
                "success",
                payload={"text": response_text, "raw": response_text, "extracted": extracted_data, "data": extracted_data},
                tokens=tokens,
                model_used=model
            )
        except Exception as e:
            logger.exception(f"Reasoning action failed: {e}")
            return ActionResult(payload.get("action_type", ActionType.SYNTHESIZE), str(agent.get("agent_id")), "failed", error=str(e))

    def _extract_search_query(self, text: str, extracted_data: Dict[str, Any]) -> Optional[str]:
        """Extract search query from various possible response formats."""
        # 1. Check extracted JSON
        query = extracted_data.get("search_query") or extracted_data.get("query")
        if query:
            return query

        arguments = extracted_data.get("arguments")
        if isinstance(arguments, dict):
            nested_query = arguments.get("query") or arguments.get("search_query")
            if isinstance(nested_query, str) and nested_query.strip():
                return nested_query.strip()
        
        # 2. Check XML-like tags
        match = re.search(r'<execute_tool>[\s\S]*?"query"\s*:\s*"([^"]+)"', text)
        if match: return match.group(1)
        
        # 3. Check SEARCH_WEB: prefix
        match = re.search(r'SEARCH_WEB:\s*(.*)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip().split("\n")[0]

        # 4. Check raw provider tool-call JSON
        match = re.search(r'"(?:query|search_query)"\s*:\s*"([^"]+)"', text)
        if match:
            return match.group(1).strip()
        
        return None

    def _parse_response(self, text: str, action_type: str = "") -> Dict[str, Any]:
        """Best-effort parser for agent responses.

        Many models will drift from strict JSON even when prompted. For CSI we
        still want to persist a usable claim/verdict rather than dropping work.
        """
        raw = (text or "").strip()

        # 1) JSON extraction (if present)
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            blob = match.group(0)
            try:
                parsed = json.loads(blob)
                if isinstance(parsed, dict):
                    return parsed
                return {"data": parsed, "raw": raw}
            except Exception:
                pass

        upper_action = (action_type or "").upper().strip()

        def _extract_confidence(s: str) -> Optional[float]:
            m = re.search(r"(?:confidence|conf)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)%?", s, re.IGNORECASE)
            if not m:
                return None
            try:
                val = float(m.group(1))
            except ValueError:
                return None
            if val > 1.0:
                val = val / 100.0 if val <= 100.0 else 1.0
            return max(0.0, min(val, 1.0))

        def _first_paragraph(s: str) -> str:
            parts = [p.strip() for p in re.split(r"\n\s*\n", s) if p.strip()]
            return parts[0] if parts else s.strip()

        # 2) Claim-like actions: extract a claim string and optional confidence.
        if upper_action in {"PROPOSE_CLAIM", "SYNTHESIZE", "DRAFT_REPORT"}:
            claim = ""
            for pat in (
                r"^\s*CLAIM\s*:\s*(.+)$",
                r"^\s*FINAL\s+ANSWER\s*:\s*(.+)$",
            ):
                m = re.search(pat, raw, re.IGNORECASE | re.MULTILINE)
                if m:
                    claim = m.group(1).strip()
                    break
            if not claim:
                claim = _first_paragraph(raw)
            claim = re.sub(r"^\s*[-*\d\.\)\]]+\s*", "", claim).strip()
            conf = _extract_confidence(raw)
            out: Dict[str, Any] = {"claim": claim, "raw": raw}
            if conf is not None:
                out["confidence"] = conf
            return out

        # 3) Verification/review-like actions: extract verdict + rationale.
        if upper_action in {"VERIFY_CLAIM", "CHALLENGE_CLAIM", "REVISE_CLAIM"}:
            verdict = None
            m = re.search(r"VERDICT\s*:\s*(supports|contradicts|needs_revision)", raw, re.IGNORECASE)
            if m:
                verdict = m.group(1).lower()
            else:
                lowered = raw.lower()
                # Heuristic: pick the strongest explicit label if present.
                for v in ("contradicts", "supports", "needs_revision"):
                    if re.search(rf"\b{v}\b", lowered):
                        verdict = v
                        break
            conf = _extract_confidence(raw)
            out = {"verdict": verdict or "needs_revision", "raw": raw}
            if conf is not None:
                out["confidence"] = conf
            return out

        return {"raw": raw}

    def _update_budgets(self, result: ActionResult):
        self.budget.current_tokens_sim += result.tokens.get("total", 0)
        self.budget.current_tokens_round += result.tokens.get("total", 0)

    def _record_telemetry(self, agent: Dict[str, Any], result: ActionResult, round_num: int):
        payload = result.payload or {}
        # Build detail: prefer explicit "detail" key; for SEARCH_WEB extract query/results from payload
        detail = payload.get("detail") or {}
        if result.action_type == ActionType.SEARCH_WEB and not detail:
            detail = {
                "query": payload.get("query", ""),
                "results_count": len(payload.get("sources", [])),
                "urls": [s.get("url", "") for s in payload.get("sources", [])[:5]],
            }
        self.store.record_agent_action(self.simulation_id, {
            "action_type": result.action_type.value,
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "role": agent.get("role"),
            "round_num": round_num,
            "status": result.status,
            "model_used": result.model_used,
            "tokens": result.tokens,
            "error": result.error,
            "detail": detail,
        })
