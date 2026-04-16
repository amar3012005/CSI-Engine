"""
Web Search Client
~~~~~~~~~~~~~~~~~
Tavily-based web search and URL content extraction for CSI Research Engine.
Optional dependency — gracefully degrades when tavily-python is not installed
or TAVILY_API_KEY is not configured.

QUALITY CONTROLS:
- Content length validation (min 100-200 chars)
- Title validation (min 5-10 chars)
- URL format validation
- Domain credibility filtering (suspicious domains)
- Ad/promotional content detection
- News article indicators (optional requirement)
- Clickbait pattern detection
- Language validation (English-only option)
- Search score thresholds
- Duplicate/repetitive content detection
- Enhanced source scoring with quality bonuses

Quality config can be customized via WebSearchClient.configure_quality() or
passed to constructor. CSI Research Engine uses strict quality settings for
research-grade source validation.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List

from ..utils.logger import get_logger

logger = get_logger("mirofish.web_search_client")

def _content_hash(url: str, content: str) -> str:
    """Generate SHA256 object hash for CSI source ID."""
    return hashlib.sha256(f"{url}::{content}".encode("utf-8")).hexdigest()[:16]

# Lazy import: tavily-python may not be installed.
_tavily_available: bool = False
_TavilyClient: Any = None

try:
    from tavily import TavilyClient as _TavilyImport  # type: ignore[import-untyped]

    _TavilyClient = _TavilyImport
    _tavily_available = True
except ImportError:
    logger.info("tavily-python not installed — web search will be unavailable")


def _tokenize_keywords(text: str, max_tokens: int = 12) -> List[str]:
    """Extract meaningful keyword tokens from text."""
    tokens = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    stopwords = {
        "the", "and", "or", "of", "to", "in", "a", "an", "for", "with", "on",
        "is", "are", "be", "this", "that", "by", "from", "as", "at", "it",
        "into", "we", "our", "their", "your", "can", "will", "should", "must",
        "http", "https", "www", "com", "org", "net",
    }
    unique: List[str] = []
    seen: set[str] = set()
    for t in tokens:
        if len(t) > 1 and t not in stopwords and t not in seen:
            unique.append(t)
            seen.add(t)
        if len(unique) >= max_tokens:
            break
    return unique


def _validate_source_quality(
    title: str, url: str, content: str, score: float, config: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Comprehensive quality validation for web sources.
    
    Args:
        config: Quality control configuration. If None, uses defaults.
    """
    if config is None:
        config = {
            "min_content_length": 100,
            "min_title_length": 5,
            "min_search_score": 0.3,
            "require_news_indicators": False,
            "strict_domain_filter": False,
            "max_ad_indicators": 3,
            "english_only": True,
        }
    
    reasons = []
    normalized_title = (title or "").strip()
    normalized_content = (content or "").strip()
    combined_text = f"{normalized_title}\n{normalized_content}".strip()
    
    # 1. Content length validation
    if len(combined_text) < config["min_content_length"]:
        reasons.append("content_too_short")
    
    # 2. Title validation
    if len(normalized_title) < config["min_title_length"]:
        reasons.append("title_too_short")
    
    # 3. URL validation
    if not url or not url.startswith(('http://', 'https://')):
        reasons.append("invalid_url")
    
    # 4. Domain credibility check
    suspicious_domains = [
        'spam', 'fake', 'scam', 'clickbait', 'viral', 'buzzfeed',
        'tabloid', 'gossip', 'sensational', 'shock', 'amazing'
    ]
    domain = url.split('/')[2] if len(url.split('/')) > 2 else ""
    
    if config["strict_domain_filter"]:
        # Stricter filtering
        if any(susp in domain.lower() for susp in suspicious_domains):
            reasons.append("suspicious_domain")
    else:
        # Basic filtering
        if any(susp in domain.lower() for susp in ['spam', 'fake', 'scam']):
            reasons.append("suspicious_domain")
    
    # 5. Content quality indicators
    content_lower = combined_text.lower()
    
    # Check for excessive ads/promotional content
    ad_indicators = ['buy now', 'click here', 'subscribe', 'newsletter', 'advertisement']
    ad_count = sum(1 for indicator in ad_indicators if indicator in content_lower)
    if ad_count > config["max_ad_indicators"]:
        reasons.append("excessive_ads")
    
    # Check for news/article indicators
    news_indicators = ['according to', 'reported', 'stated', 'said', 'announced', 'published']
    news_score = sum(1 for indicator in news_indicators if indicator in content_lower)
    
    if config["require_news_indicators"] and news_score == 0:
        reasons.append("no_news_indicators")
    
    # Check for listicle/clickbait patterns
    if title.lower().startswith(('10 ', '5 ', '7 ', 'top ', 'best ', 'worst ')):
        reasons.append("clickbait_title")
    
    # 6. Language detection
    if config["english_only"]:
        english_chars = sum(1 for c in combined_text if c.isascii())
        total_chars = len(combined_text)
        if total_chars > 50 and (english_chars / total_chars) < 0.8:
            reasons.append("non_english_content")
    
    # 7. Score threshold
    if score < config["min_search_score"]:
        reasons.append("low_search_score")
    
    # 8. Duplicate content detection (basic)
    words = combined_text.split()
    if len(words) > 200:
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1
        max_freq = max(word_freq.values()) if word_freq else 0
        if max_freq > len(words) * 0.08:
            reasons.append("repetitive_content")
    
    return {
        "valid": len(reasons) == 0,
        "reasons": reasons,
        "quality_score": max(0, score - len(reasons) * 0.1),
        "news_score": news_score,
        "content_length": len(content),
        "has_news_indicators": news_score > 0
    }


class WebSearchClient:
    """Tavily-based web search and URL content extraction."""

    # Class-level rate-limit state (shared across all instances in one process)
    _last_search_ts: float = 0.0
    _MIN_SEARCH_GAP: float = 2.0  # light guard; 429 retry handles overflow
    _core_quota_exhausted: bool = False
    _core_quota_exhausted_logged: bool = False

    def __init__(self, api_key: str | None = None, quality_config: Dict[str, Any] | None = None) -> None:
        self._api_key: str = api_key or os.environ.get("TAVILY_API_KEY", "")
        self._client: Any = None
        
        # Quality control configuration
        self._quality_config = quality_config or {
            "min_content_length": 100,
            "min_title_length": 5,
            "min_search_score": 0.3,
            "require_news_indicators": False,
            "strict_domain_filter": False,
            "max_ad_indicators": 3,
            "english_only": True,
        }

    def _ensure_client(self) -> bool:
        """Lazily initialise the Tavily client. Returns True on success."""
        if self._client is not None:
            return True
        if not _tavily_available:
            return False
        if not self._api_key:
            logger.warning("TAVILY_API_KEY not set — web search disabled")
            return False
        try:
            self._client = _TavilyClient(api_key=self._api_key)
            return True
        except Exception as exc:
            logger.warning("Failed to initialise Tavily client: %s", exc)
            return False

    def is_available(self) -> bool:
        """Check if web search is available (Tavily or HIVEMIND Core fallback)."""
        if self._ensure_client():
            return True
        # Even without Tavily, the HIVEMIND Core API fallback may work
        try:
            from ..config import Config
            hivemind_url = getattr(Config, "HIVEMIND_API_URL", "")
            hivemind_key = getattr(Config, "HIVEMIND_API_KEY", "")
            if hivemind_url and hivemind_key:
                return True
            # Check hardcoded core URL as last resort
            if hivemind_key:
                return True
        except Exception:
            pass
        return False

    def _throttle(self) -> None:
        """Enforce minimum gap between web searches to stay under rate limits."""
        import time
        now = time.monotonic()
        elapsed = now - WebSearchClient._last_search_ts
        if elapsed < self._MIN_SEARCH_GAP:
            wait = self._MIN_SEARCH_GAP - elapsed
            logger.debug("Throttling web search for %.1fs", wait)
            time.sleep(wait)
        WebSearchClient._last_search_ts = time.monotonic()

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        topic: str = "general",
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Search the web. Returns list of {title, url, content, score}."""
        self._throttle()
        if not self._ensure_client():
            return self._hivemind_core_fallback(query, max_results)
        try:
            kwargs: Dict[str, Any] = {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
                "include_raw_content": False,
                "include_answer": True,
                "topic": topic,
            }
            if topic == "news":
                kwargs["days"] = days
                
            response = self._client.search(**kwargs)
            results: List[Dict[str, Any]] = []
            
            # If Tavily provided a synthesized answer, prepend it as a primary source
            answer = response.get("answer")
            if answer and answer.strip():
                results.append({
                    "title": f"Tavily Synthesis: {query[:30]}...",
                    "url": "tavily:synthesis",
                    "content": answer,
                    "score": 1.0,
                })
                
            for item in response.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""), # Only use the summarized content
                    "score": float(item.get("score", 0.5) or 0.5),
                })
            return results
        except Exception as exc:
            logger.warning("Tavily search failed for query '%s': %s", query, exc)
            return self._hivemind_core_fallback(query, max_results)

    def _hivemind_core_fallback(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Fallback to HIVEMIND Core API (web intelligence / LightPanda).

        Handles 429 rate-limits with exponential backoff (server allows 10/min,
        60/hour, 50/day).  On 0 results, retries once with a simplified query.
        """
        if WebSearchClient._core_quota_exhausted:
            if not WebSearchClient._core_quota_exhausted_logged:
                logger.error("HIVEMIND Core search disabled: daily quota exhausted")
                WebSearchClient._core_quota_exhausted_logged = True
            return []

        logger.info("Falling back to HIVEMIND Core API for query: '%s'", query)
        try:
            import requests
            import time
            from ..config import Config

            base_url = getattr(Config, "HIVEMIND_API_URL", "").rstrip("/")
            api_key = getattr(Config, "HIVEMIND_API_KEY", "")

            CORE_URL = "https://core.hivemind.davinciai.eu:8050"
            candidate_urls = []
            if base_url:
                candidate_urls.append(base_url)
            if CORE_URL not in candidate_urls:
                candidate_urls.append(CORE_URL)

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # Try each candidate URL until one succeeds
            last_exc: Exception | None = None
            for url in candidate_urls:
                try:
                    results = self._poll_hivemind_search(url, query, max_results, headers)
                    # If 0 results, retry once with a simplified query
                    if not results:
                        simple_q = self._simplify_query(query)
                        if simple_q != query:
                            logger.info("Retrying with simplified query: '%s'", simple_q)
                            results = self._poll_hivemind_search(url, simple_q, max_results, headers)
                    return results
                except RuntimeError as exc:
                    if "quota_exceeded" in str(exc):
                        WebSearchClient._core_quota_exhausted = True
                        WebSearchClient._core_quota_exhausted_logged = True
                        logger.error("HIVEMIND Core search quota exhausted; skipping further Core retries")
                        return []
                    logger.warning("HIVEMIND Core fallback via %s failed: %s", url, exc)
                    last_exc = exc
                except Exception as exc:
                    logger.warning("HIVEMIND Core fallback via %s failed: %s", url, exc)
                    last_exc = exc

            logger.error("All HIVEMIND Core API URLs exhausted for query '%s': %s", query, last_exc)
            return []

        except Exception as fallback_exc:
            logger.error("HIVEMIND Core API fallback failed for query '%s': %s", query, fallback_exc)
            return []

    @staticmethod
    def _simplify_query(query: str) -> str:
        """Shorten long/complex queries to improve search hit rate."""
        # Strip commas that concatenate multiple sub-queries
        parts = [p.strip() for p in query.split(",") if p.strip()]
        if len(parts) > 1:
            # Take the first meaningful segment (usually the most specific)
            return parts[0][:120]
        # If single segment but very long, truncate to first ~8 words
        words = query.split()
        if len(words) > 10:
            return " ".join(words[:8])
        return query

    def _poll_hivemind_search(
        self, base_url: str, query: str, max_results: int, headers: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Submit a search job and poll until done.

        Retries up to 3 times on 429 with exponential backoff.
        """
        import requests
        import time

        # ── Submit with 429 retry ──
        backoff = 4  # seconds
        for retry in range(3):
            submit_resp = requests.post(
                f"{base_url}/api/web/search/jobs",
                json={"query": query, "limit": max_results},
                headers=headers,
                timeout=15,
            )
            if submit_resp.status_code in {401, 402, 403, 429}:
                try:
                    err_payload = submit_resp.json()
                except Exception:
                    err_payload = {}
                err_code = str(err_payload.get("code") or err_payload.get("error") or "")
                if "quota_exceeded" in err_code:
                    raise RuntimeError(f"quota_exceeded: {err_payload}")
            if submit_resp.status_code == 429:
                retry_after = int(submit_resp.headers.get("Retry-After", backoff))
                wait = max(retry_after, backoff)
                logger.info("Rate limited (429), waiting %ds before retry %d/3", wait, retry + 1)
                time.sleep(wait)
                backoff = min(backoff * 2, 30)
                continue
            submit_resp.raise_for_status()
            break
        else:
            submit_resp.raise_for_status()  # final raise

        job_id = submit_resp.json().get("job_id")
        if not job_id:
            raise ValueError("No job_id returned from HIVEMIND API")

        # Poll — up to ~30 s
        for attempt in range(15):
            time.sleep(2)
            status_resp = requests.get(
                f"{base_url}/api/web/jobs/{job_id}",
                headers=headers,
                timeout=15,
            )
            status_resp.raise_for_status()
            data = status_resp.json()
            status = data.get("status")

            if status == "succeeded":
                results = data.get("results", [])
                final: List[Dict[str, Any]] = []
                for item in results:
                    final.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": (
                            item.get("snippet", "")
                            or item.get("content", "")
                            or item.get("text", "")
                        ),
                        "score": float(item.get("score", 0.5) or 0.5),
                    })
                logger.info(
                    "HIVEMIND Core search returned %d results (job %s, attempt %d)",
                    len(final), job_id, attempt + 1,
                )
                return final
            elif status == "failed":
                raise RuntimeError(
                    f"HIVEMIND search job {job_id} failed: {data.get('error')}"
                )

        raise TimeoutError(f"HIVEMIND search job {job_id} still running after 30 s")

    def extract(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Extract full content from URLs. Returns list of {url, content, title}."""
        if not self._ensure_client():
            return []
        if not urls:
            return []
        try:
            response = self._client.extract(urls=urls[:5])
            results: List[Dict[str, Any]] = []
            for item in response.get("results", []):
                results.append({
                    "url": item.get("url", ""),
                    "content": item.get("raw_content", "") or item.get("content", ""),
                    "title": item.get("title", ""),
                })
            return results
        except Exception as exc:
            logger.warning("Tavily extract failed for %d URLs: %s", len(urls), exc)
            return []

    def search_as_csi_sources(
        self,
        query: str,
        agent_name: str,
        round_num: int,
        max_results: int = 5,
        search_depth: str = "advanced",
    ) -> List[Dict[str, Any]]:
        """Search and return results pre-formatted as CSI source dicts.
        
        Includes comprehensive quality validation to ensure source accuracy.
        """
        raw_results = self.search(
            query=query,
            max_results=max_results * 2,  # Get more results to allow for filtering
            search_depth=search_depth,
        )
        
        sources: List[Dict[str, Any]] = []
        quality_stats = {"total": len(raw_results), "accepted": 0, "rejected": 0, "reasons": {}}
        relaxed_config = {
            **self._quality_config,
            "min_content_length": min(int(self._quality_config.get("min_content_length", 100)), 50),
            "min_title_length": min(int(self._quality_config.get("min_title_length", 5)), 3),
            "min_search_score": min(float(self._quality_config.get("min_search_score", 0.3)), 0.1),
            "strict_domain_filter": False,
            "max_ad_indicators": max(int(self._quality_config.get("max_ad_indicators", 3)), 5),
        }
        deferred_results: List[Dict[str, Any]] = []

        def _append_source(result: Dict[str, Any], quality_check: Dict[str, Any]) -> None:
            content = result.get("content", "")
            title = result.get("title", "")
            url = result.get("url", "")
            source_id = f"csi_source_web_{_content_hash(url, content)}"
            sources.append({
                "source_id": source_id,
                "source_type": "web",
                "title": title,
                "url": url,
                "content": content,
                "summary": content[:500],
                "origin": "web_search",
                "priority": quality_check["quality_score"],
                "keywords": _tokenize_keywords(f"{title} {content}"),
                "metadata": {
                    "discovered_by": agent_name,
                    "search_query": query,
                    "round_num": round_num,
                    "quality_check": quality_check,
                    "search_score": float(result.get("score", 0.5) or 0.5),
                },
            })
        
        for result in raw_results:
            content = result.get("content", "")
            title = result.get("title", "")
            url = result.get("url", "")
            score = float(result.get("score", 0.5) or 0.5)
            
            # Quality validation
            quality_check = _validate_source_quality(title, url, content, score, self._quality_config)
            
            # Update stats
            if quality_check["valid"]:
                quality_stats["accepted"] += 1
            else:
                quality_stats["rejected"] += 1
                for reason in quality_check["reasons"]:
                    quality_stats["reasons"][reason] = quality_stats["reasons"].get(reason, 0) + 1
                deferred_results.append(result)
            
            # Only include high-quality sources
            if not quality_check["valid"]:
                logger.debug(
                    "Rejected source '%s' (%s): %s", 
                    title[:50], url, ", ".join(quality_check["reasons"])
                )
                continue

            _append_source(result, quality_check)

        if not sources and deferred_results:
            logger.info(
                "Web search relaxed fallback engaged for query '%s' after 0/%d strict matches",
                query[:80],
                len(raw_results),
            )
            for result in deferred_results:
                relaxed_check = _validate_source_quality(
                    result.get("title", ""),
                    result.get("url", ""),
                    result.get("content", ""),
                    float(result.get("score", 0.5) or 0.5),
                    relaxed_config,
                )
                if relaxed_check["valid"]:
                    _append_source(result, relaxed_check)
                    if len(sources) >= max_results:
                        break
        
        logger.info(
            "Web search quality filter: %d/%d strict matches for query '%s' (agent: %s, top_rejections=%s, final_sources=%d)",
            quality_stats["accepted"],
            quality_stats["total"],
            query[:50],
            agent_name,
            quality_stats["reasons"],
            len(sources),
        )
        
        # Return only the requested number of high-quality sources
        return sources[:max_results]

    def configure_quality(self, config: Dict[str, Any]) -> None:
        """Configure quality control settings.
        
        Args:
            config: Dict with quality settings:
                - min_content_length: Minimum content length (default: 100)
                - min_title_length: Minimum title length (default: 5)
                - min_search_score: Minimum search score threshold (default: 0.3)
                - require_news_indicators: Require news-like content (default: False)
                - strict_domain_filter: Strict domain filtering (default: False)
                - max_ad_indicators: Max ad indicators allowed (default: 3)
                - english_only: Require English content (default: True)
        """
        self._quality_config.update(config)
        logger.info("Updated web search quality config: %s", self._quality_config)

    def get_quality_stats(self) -> Dict[str, Any]:
        """Get current quality configuration and recent statistics."""
        return {
            "config": self._quality_config.copy(),
            "available": self.is_available(),
        }

    def extract_as_csi_sources(
        self,
        urls: List[str],
        agent_name: str,
        round_num: int,
    ) -> List[Dict[str, Any]]:
        """Extract URL content and return as CSI source dicts.
        
        Includes quality validation for extracted content.
        """
        raw_results = self.extract(urls=urls)
        sources: List[Dict[str, Any]] = []
        
        for result in raw_results:
            content = result.get("content", "")
            title = result.get("title", "")
            url = result.get("url", "")
            
            # Quality validation for extracted content
            quality_check = _validate_source_quality(title, url, content, 0.8, self._quality_config)
            
            if not quality_check["valid"]:
                logger.debug(
                    "Rejected extracted source '%s' (%s): %s", 
                    title[:50], url, ", ".join(quality_check["reasons"])
                )
                continue
            
            source_id = f"csi_source_web_{_content_hash(url, content)}"
            sources.append({
                "source_id": source_id,
                "source_type": "web",
                "title": title,
                "url": url,
                "content": content,
                "summary": content[:500],
                "origin": "url_extraction",
                "priority": quality_check["quality_score"],
                "keywords": _tokenize_keywords(f"{title} {content}"),
                "metadata": {
                    "discovered_by": agent_name,
                    "round_num": round_num,
                    "quality_check": quality_check,
                    "extraction_method": "deep_read",
                },
            })
        
        logger.info(
            "URL extraction: %d/%d sources passed quality validation",
            len(sources), len(raw_results)
        )
        
        
        return sources
