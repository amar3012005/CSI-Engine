"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
import random
import threading
import time
import ast
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config
from .logger import get_logger
from .token_usage_tracker import TokenUsageTracker

logger = get_logger("mirofish.llm_client")


class LLMClient:
    """LLM客户端"""
    _model_semaphores: Dict[str, threading.Semaphore] = {}
    _semaphore_lock = threading.Lock()
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        usage_scope: Optional[str] = None,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        self.usage_scope = usage_scope
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    @classmethod
    def _get_model_semaphore(cls, model: str) -> threading.Semaphore:
        key = model or "default"
        with cls._semaphore_lock:
            if key not in cls._model_semaphores:
                cls._model_semaphores[key] = threading.Semaphore(2)
            return cls._model_semaphores[key]

    def _create_completion_with_retry(self, kwargs: Dict[str, Any]):
        delay = 2.0
        semaphore = self._get_model_semaphore(self.model)
        with semaphore:
            for attempt in range(6):
                try:
                    return self.client.chat.completions.create(**kwargs)
                except Exception as e:
                    error_str = str(e)
                    is_rate_limit = (
                        "rate_limit_exceeded" in error_str
                        or "Rate limit" in error_str
                        or "429" in error_str
                    )
                    if not is_rate_limit or attempt >= 5:
                        raise

                    retry_after = None
                    body = getattr(e, "body", None)
                    if isinstance(body, dict):
                        message = str(body.get("message") or body.get("error", {}).get("message") or "")
                    else:
                        message = error_str
                    match = re.search(r"try again in\s+([0-9.]+)s", message, re.IGNORECASE)
                    if match:
                        try:
                            retry_after = float(match.group(1))
                        except ValueError:
                            retry_after = None

                    wait = max(retry_after or 0, delay) + random.uniform(0, 0.5)
                    logger.warning(
                        "LLM rate limited for model %s; retrying in %.1fs (%d/5)",
                        self.model,
                        wait,
                        attempt + 1,
                    )
                    time.sleep(wait)
                    delay = min(delay * 2, 30.0)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        search_settings: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            search_settings: Optional search settings for Groq Compound
            
        Returns:
            模型响应文本
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        model_name = (self.model or "").lower()
        is_groq_compound = model_name == "groq/compound"
        
        # Support search_settings for Groq Compound without forcing native tool choice.
        # The research engine handles SEARCH_WEB intent in text form because provider-side
        # tool registration for groq/compound is inconsistent and caused 400 failures.
        if search_settings and is_groq_compound:
            kwargs["extra_body"] = {"search_settings": search_settings}
            
        # Use Groq reasoning models are stricter on token params.
        if "gpt-oss" in (self.model or ""):
            kwargs["max_completion_tokens"] = max_tokens
            if "extra_body" not in kwargs:
                kwargs["extra_body"] = {}
            kwargs["extra_body"]["include_reasoning"] = False
            kwargs["temperature"] = max(0.0, min(temperature, 0.7))
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens
        
        # Groq Compound exposes built-in tools and should be called with tool_choice=auto
        # but without custom tool definitions. Other compound-like adapters still
        # use the legacy explicit function schema below.
        if is_groq_compound:
            # We must NOT pass tool_choice or tools if we want to avoid 400 errors 
            # when the provider configuration is mismatched.
            # We let the model output SEARCH_WEB: "..." and parse it in the engine.
            pass
        elif "compound" in model_name:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web for real-time information and news.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "queries": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of search queries"
                                }
                            },
                            "required": ["queries"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "visit_website",
                        "description": "Visit a specific URL to extract full content.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "The URL to visit"}
                            },
                            "required": ["url"]
                        }
                    }
                }
            ]
            kwargs["tool_choice"] = "auto"

        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = self._create_completion_with_retry(kwargs)
        except Exception as e:
            error_str = str(e)
            # Handle models that don't support tool calling by retrying without tools
            if "tool calling` is not supported" in error_str or "invalid_request_error" in error_str and "tool calling" in error_str:
                logger.warning(f"Model {self.model} does not support tool calling. Retrying without tools.")
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)
                # Also remove search_settings if they were triggering tool use
                if "extra_body" in kwargs and "search_settings" in kwargs["extra_body"]:
                    kwargs["extra_body"].pop("search_settings")
                response = self._create_completion_with_retry(kwargs)
            # Some providers/models reject response_format=json_object.
            elif response_format:
                logger.warning(f"LLM JSON模式失败，回退普通文本解析: {e}")
                kwargs.pop("response_format", None)
                response = self._create_completion_with_retry(kwargs)
            elif any(sig in error_str for sig in ("tool_use_failed", "output_parse_failed", "failed_generation")) or "tool_choice" in error_str.lower():
                # Groq / some providers reject when model generates a native tool
                # call but no tools are registered in the request.  The error body
                # contains the generation the model *wanted* to produce in
                # ``failed_generation``.  Extract it and return it as the response
                # so the report agent's text-based tool parser can handle it.
                logger.warning(
                    "Model attempted native tool call without tools registered or provider rejected the tool cycle — "
                    "extracting failed_generation as response: %s", e,
                )
                import json as _json
                failed_gen = ""
                try:
                    # OpenAI SDK wraps the body; try to get the raw dict
                    err_body = getattr(e, "body", None) or {}
                    if isinstance(err_body, str):
                        err_body = _json.loads(err_body)
                    if isinstance(err_body, dict):
                        failed_gen = err_body.get("failed_generation", "") or ""
                        if not failed_gen:
                            err_inner = err_body.get("error", {})
                            if isinstance(err_inner, dict):
                                failed_gen = err_inner.get("failed_generation", "") or ""
                except Exception:
                    pass
                if not failed_gen:
                    # Try regex on the string representation
                    fg_match = re.search(r"'failed_generation':\s*'(.*?)'", error_str)
                    if fg_match:
                        failed_gen = fg_match.group(1)
                if failed_gen:
                    # Groq wraps tool calls as:
                    #   {"name":"tool_call","arguments":{"name":"query_claims","parameters":{...}}}
                    # Unwrap to get the real tool name and parameters.
                    try:
                        parsed = _json.loads(failed_gen)
                        if isinstance(parsed, dict):
                            cur = parsed
                            # Peel common provider wrappers:
                            # {name, arguments:{name, parameters:{...}}}
                            # {name, arguments:{name, arguments:{...}}}
                            for _ in range(4):
                                args = cur.get("arguments")
                                if isinstance(args, dict) and "name" in args:
                                    cur = args
                                    continue
                                break
                            if isinstance(cur, dict) and "name" in cur:
                                real_name = cur.get("name")
                                real_params = cur.get("parameters")
                                if real_params is None and isinstance(cur.get("arguments"), dict):
                                    # Some models nest parameters under "arguments"
                                    real_params = cur.get("arguments")
                                if not isinstance(real_params, dict):
                                    real_params = {}
                                failed_gen = _json.dumps(
                                    {"name": real_name, "parameters": real_params},
                                    ensure_ascii=False,
                                )
                    except (_json.JSONDecodeError, TypeError):
                        pass
                    # Wrap as XML tool_call so the report agent parser can pick it up
                    return f"<execute_tool>\n{failed_gen}\n</execute_tool>"
                raise
            else:
                raise

        usage = getattr(response, "usage", None)
        if usage and self.usage_scope:
            TokenUsageTracker.record_usage(
                self.usage_scope,
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
                model=self.model,
                source="llm_client",
            )

        content = response.choices[0].message.content
        if not content and response.choices and getattr(response.choices[0], "message", None):
            # Defensive fallback for providers that return empty content with reasoning traces.
            content = getattr(response.choices[0].message, "reasoning", "") or ""
        
        # Groq/Compound Native Search Extraction:
        # If content is empty but executed_tools contains search results, we wrap them
        # so they can be ingested by the CSI engine.
        msg = response.choices[0].message
        if not content and hasattr(msg, 'executed_tools') and msg.executed_tools:
            for tool in msg.executed_tools:
                if tool.type == 'search' and hasattr(tool, 'search_results') and tool.search_results:
                    # Format as a mock tool call for the engine parser
                    content = f"<execute_tool>\n{{\"name\": \"web_search\", \"parameters\": {json.dumps(tool.search_results)}}}\n</execute_tool>"
                    break

        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content

    def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        if "gpt-oss" in (self.model or ""):
            kwargs["max_completion_tokens"] = max_tokens
            kwargs["extra_body"] = {"include_reasoning": False}
            kwargs["temperature"] = max(0.0, min(temperature, 0.7))
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens

        try:
            response = self._create_completion_with_retry(kwargs)
        except Exception as e:
            error_str = str(e)
            if "tool calling" in error_str.lower() or "tools" in error_str.lower():
                logger.warning("Tool calling unavailable for model %s; falling back to text protocol.", self.model)
                return {
                    "content": self.chat(messages=messages, temperature=temperature, max_tokens=max_tokens),
                    "tool_calls": [],
                }
            raise

        usage = getattr(response, "usage", None)
        if usage and self.usage_scope:
            TokenUsageTracker.record_usage(
                self.usage_scope,
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
                model=self.model,
                source="llm_client_tools",
            )

        message = response.choices[0].message
        parsed_tool_calls = []
        for tool_call in getattr(message, "tool_calls", None) or []:
            function = getattr(tool_call, "function", None)
            if not function:
                continue
            arguments = getattr(function, "arguments", "") or "{}"
            try:
                parameters = json.loads(arguments)
            except json.JSONDecodeError:
                parameters = {}
            parsed_tool_calls.append({
                "id": getattr(tool_call, "id", ""),
                "name": getattr(function, "name", ""),
                "parameters": parameters,
            })

        content = getattr(message, "content", None) or ""
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return {"content": content, "tool_calls": parsed_tool_calls}
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        # 清理markdown代码块标记
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        def _strip_to_json_blob(text: str) -> str:
            """Extract a likely JSON blob from a mixed response."""
            text = (text or "").strip()
            if not text:
                return ""
            first_obj = text.find("{")
            first_arr = text.find("[")
            if first_obj == -1 and first_arr == -1:
                return text
            start = min([i for i in (first_obj, first_arr) if i != -1])
            end_obj = text.rfind("}")
            end_arr = text.rfind("]")
            end = max(end_obj, end_arr)
            if end != -1 and end > start:
                return text[start : end + 1].strip()
            return text[start:].strip()

        def _repair_common_json(text: str) -> str:
            # Remove trailing commas before } or ]
            text = re.sub(r",\s*([}\]])", r"\1", text)
            # Remove JS-style // comments
            text = re.sub(r"//[^\n]*", "", text)
            # Normalize smart quotes
            text = (
                text.replace("\u201c", "\"")
                .replace("\u201d", "\"")
                .replace("\u2018", "'")
                .replace("\u2019", "'")
            )
            # Remove leading BOM / control chars
            text = re.sub(r"^[\ufeff\000-\010\013\014\016-\037]+", "", text)
            return text.strip()

        def _lenient_loads(text: str) -> Dict[str, Any]:
            blob = _repair_common_json(_strip_to_json_blob(text))
            if not blob:
                raise ValueError("LLM returned empty response")

            # 1) Strict JSON
            try:
                parsed = json.loads(blob)
                if isinstance(parsed, dict):
                    return parsed
                return {"data": parsed}
            except Exception:
                pass

            # 2) Try extracting the first {...} block
            match = re.search(r"\{[\s\S]*\}", blob)
            if match:
                candidate = _repair_common_json(match.group(0))
                try:
                    return json.loads(candidate)
                except Exception:
                    blob = candidate

            # 3) Python literal fallback (single quotes, etc.)
            lit = ast.literal_eval(blob)
            if isinstance(lit, dict):
                return lit
            return {"data": lit}

        try:
            return _lenient_loads(cleaned_response)
        except Exception as exc:
            raise ValueError(f"LLM返回的JSON格式无效: {cleaned_response}") from exc
