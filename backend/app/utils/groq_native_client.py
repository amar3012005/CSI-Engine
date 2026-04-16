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
        
    def chat_with_tools(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.5,
        max_tokens: int = 4096
    ) -> str:
        """
        Execute a native tool-calling turn.
        Note: This uses Groq's specialized 'compound' model which maps 
        model-generated intents to internal search/browse actions.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "groq/compound",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tool_choice": "auto"
        }

        # Compound models handle search NATIVELY and do not require explicit tool definitions
        # in the 'tools' array if they are built-in tools like web_search.
        # Including them can cause 400 'Unexpected tool' or 'No tools provided' errors.
        
        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=60)
            if response.status_code == 400:
                 error_data = response.json()
                 # Check if the error contains 'failed_generation' which usually indicates 
                 # the model's internal search failed but we have a text fallback
                 if "failed_generation" in str(error_data):
                      logger.warning("Groq tool call partially failed, extracting failed_generation text")
                      return error_data.get("error", {}).get("failed_generation", "Search failed.")
            
            response.raise_for_status()
            data = response.json()
            
            # The compound model returns the final synthesized answer 
            # after internal search/browse cycles.
            return data["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"Groq Native Turn failed: {str(e)}")
            raise
