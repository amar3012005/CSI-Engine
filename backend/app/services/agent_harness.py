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
    Owns routing, budgeting, validation, and telemetry.
    """

    def __init__(
        self,
        simulation_id: str,
        llm_client: LLMClient,
        budget: Optional[ActionBudget] = None,
        store: Optional[Any] = None,
        web_client: Optional[Any] = None,
        config_mode: str = 'web_research',
    ):
        self.simulation_id = simulation_id
        self.llm = llm_client
        self.budget = budget or ActionBudget()
        self.store = store
        self.web_client = web_client
        self.config_mode = config_mode
        
        # Model mapping
        self.MODEL_SEARCH = "groq/compound"
        self.MODEL_REASONING = "gpt-oss-20b" # Default for most actions

    def execute(
        self,
        action_type: Union[ActionType, str],
        agent: Dict[str, Any],
        payload: Dict[str, Any],
        round_num: int = 1
    ) -> ActionResult:
        """EntryPoint for all agent actions."""
        if isinstance(action_type, str):
            try:
                action_type = ActionType(action_type)
            except ValueError:
                return ActionResult(ActionType.SYNTHESIZE, str(agent.get("agent_id")), "failed", error=f"Unknown action type: {action_type}")

        # 1. Budget check
        if self.budget.current_tokens_sim >= self.budget.max_tokens_per_simulation:
            return ActionResult(action_type, str(agent.get("agent_id")), "budget_exceeded", error="Simulation token budget exceeded")

        # 2. Routing & Model Selection
        target_model = self.MODEL_REASONING
        if action_type == ActionType.SEARCH_WEB:
            target_model = self.MODEL_SEARCH

        # 3. Action Execution Dispatch
        try:
            handler = self._get_handler(action_type)
            result = handler(agent, payload, round_num, target_model)
            
            # 4. Telemetry Update
            self._update_budgets(result)
            
            # 5. Record action if store is available
            if self.store and hasattr(self.store, "record_agent_action"):
                self._record_telemetry(agent, result, round_num)
                
            return result
        except Exception as e:
            logger.exception(f"Action {action_type} failed for agent {agent.get('agent_id')}")
            return ActionResult(action_type, str(agent.get("agent_id")), "failed", error=str(e))

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
            
            # Extraction logic (migrated from engine)
            extracted_data = self._parse_response(response_text)
            
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

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Unified parser for agent responses."""
        # Simple JSON extraction as baseline
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        return {"raw": text}

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
