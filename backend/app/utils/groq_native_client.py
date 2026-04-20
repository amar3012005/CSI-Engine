import os
import json
import requests
from typing import List, Dict, Any, Optional
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("mirofish.groq_native_client")

class GroqNativeClient:
    """
    Groq Native Tool-Calling Client for CSI Personas.
    Enables 'Native Intelligence' turns (Reason + Search + Browse).
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY") or Config.LLM_API_KEY
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "groq/compound" 

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _post_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        search_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("Groq API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if search_settings:
            payload["search_settings"] = search_settings

        response = requests.post(self.base_url, headers=headers, json=payload, timeout=60)
        if response.status_code == 400:
            error_data = response.json()
            if "failed_generation" in str(error_data):
                logger.warning("Groq tool call partially failed, returning error payload")
                return {"error": error_data.get("error", {})}

        response.raise_for_status()
        return response.json()
        
    def chat_with_tools(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.5,
        max_tokens: int = 4096,
        search_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Execute a native tool-calling turn.
        Note: This uses Groq's specialized 'compound' model which maps 
        model-generated intents to internal search/browse actions.
        """
        try:
            data = self._post_chat_completion(messages, temperature, max_tokens, search_settings=search_settings)
            if "error" in data:
                return data.get("error", {}).get("failed_generation", "Search failed.")

            # The compound model returns the final synthesized answer 
            # after internal search/browse cycles.
            return data["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"Groq Native Turn failed: {str(e)}")
            raise

    def web_search(
        self,
        query: str,
        max_results: int = 5,
        search_settings: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        messages = [{"role": "user", "content": query}]
        data = self._post_chat_completion(
            messages=messages,
            temperature=0.2,
            max_tokens=1024,
            search_settings=search_settings,
        )
        if "error" in data:
            logger.warning("Groq native search returned error payload for query '%s'", query)
            return []

        usage = data.get("usage") or {}
        if usage:
            logger.info(
                "Groq native search usage for query '%s': prompt=%s completion=%s total=%s",
                query,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
            )

        choices = data.get("choices", [])
        if not choices:
            return []

        message = choices[0].get("message", {})
        executed_tools = message.get("executed_tools") or []

        results: List[Dict[str, Any]] = []
        for tool_call in executed_tools:
            search_results = tool_call.get("search_results") or []
            if isinstance(search_results, dict):
                items = search_results.get("results", [])
            else:
                items = search_results
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": float(item.get("score", 0.5) or 0.5),
                })

        if not results and message.get("content"):
            logger.info(
                "Groq native search returned synthesized text without tool results for query '%s'",
                query,
            )

        return results[:max_results]
