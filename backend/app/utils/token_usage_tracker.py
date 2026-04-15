import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from ..config import Config
from .logger import get_logger

logger = get_logger("mirofish.token_usage")


class TokenUsageTracker:
    """Persist exact provider-reported token usage per simulation/session scope."""

    _lock = threading.RLock()

    @classmethod
    def _path(cls, scope_id: str) -> str:
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, scope_id)
        os.makedirs(sim_dir, exist_ok=True)
        return os.path.join(sim_dir, "token_usage.json")

    @classmethod
    def _default_payload(cls, scope_id: str) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "scope_id": scope_id,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "calls": 0,
            "models": {},
            "sources": {},
            "updated_at": now,
            "created_at": now,
        }

    @classmethod
    def get_usage(cls, scope_id: str) -> Dict[str, Any]:
        path = cls._path(scope_id)
        with cls._lock:
          if not os.path.exists(path):
              return cls._default_payload(scope_id)
          try:
              with open(path, "r", encoding="utf-8") as f:
                  data = json.load(f)
              if isinstance(data, dict):
                  return data
          except Exception as exc:
              logger.warning("Failed to read token usage for %s: %s", scope_id, exc)
          return cls._default_payload(scope_id)

    @classmethod
    def reset_usage(cls, scope_id: str) -> Dict[str, Any]:
        payload = cls._default_payload(scope_id)
        path = cls._path(scope_id)
        with cls._lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        return payload

    @classmethod
    def record_usage(
        cls,
        scope_id: Optional[str],
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        model: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not scope_id:
            return {}

        path = cls._path(scope_id)
        with cls._lock:
            payload = cls.get_usage(scope_id)
            payload["input_tokens"] = int(payload.get("input_tokens", 0) or 0) + int(prompt_tokens or 0)
            payload["output_tokens"] = int(payload.get("output_tokens", 0) or 0) + int(completion_tokens or 0)
            payload["total_tokens"] = int(payload.get("total_tokens", 0) or 0) + int(total_tokens or (prompt_tokens or 0) + (completion_tokens or 0))
            payload["calls"] = int(payload.get("calls", 0) or 0) + 1
            payload["updated_at"] = datetime.now().isoformat()

            if model:
                models = payload.setdefault("models", {})
                models[model] = int(models.get(model, 0) or 0) + int(total_tokens or (prompt_tokens or 0) + (completion_tokens or 0))

            if source:
                sources = payload.setdefault("sources", {})
                sources[source] = int(sources.get(source, 0) or 0) + int(total_tokens or (prompt_tokens or 0) + (completion_tokens or 0))

            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return payload
