"""
Local CSI working state for a single simulation.

This keeps all research artifacts inside:
  backend/uploads/simulations/<sim_id>/csi/*

The store is intentionally file-based so it can be used without HIVEMIND.
It seeds sources from the prepare inputs, then writes claims, trials,
agent actions, recalls, and relations as append-only local artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger
from .text_processor import TextProcessor

logger = get_logger("mirofish.simulation_csi_local")


class SimulationCSILocalStore:
    """Simulation-scoped local CSI store."""

    _lock = threading.RLock()

    def _sim_dir(self, simulation_id: str) -> str:
        return os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

    def _csi_dir(self, simulation_id: str) -> str:
        path = os.path.join(self._sim_dir(simulation_id), "csi")
        os.makedirs(path, exist_ok=True)
        return path

    def _path(self, simulation_id: str, filename: str) -> str:
        return os.path.join(self._csi_dir(simulation_id), filename)

    def _now(self) -> str:
        return datetime.now().isoformat()

    def _load_json(self, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _append_jsonl(self, path: str, record: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_jsonl(self, path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def _stable_hash(self, payload: Dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
        stopwords = {
            "the", "and", "or", "of", "to", "in", "a", "an", "for", "with", "on",
            "is", "are", "be", "this", "that", "by", "from", "as", "at", "it",
            "into", "we", "our", "their", "your", "can", "will", "should", "must",
        }
        return [t for t in tokens if len(t) > 1 and t not in stopwords]

    def _unique(self, values: List[str]) -> List[str]:
        seen = set()
        ordered = []
        for value in values:
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    def _entity_id(self, simulation_id: str, kind: str, key: str) -> str:
        digest = self._stable_hash({"simulation_id": simulation_id, "kind": kind, "key": key})[:20]
        return f"csi_{kind}_{digest}"

    def _load_state(self, simulation_id: str) -> Dict[str, Any]:
        default = {
            "simulation_id": simulation_id,
            "initialized": False,
            "round_count": 0,
            "source_count": 0,
            "claim_count": 0,
            "trial_count": 0,
            "agent_action_count": 0,
            "recall_count": 0,
            "relation_count": 0,
            "created_at": self._now(),
            "updated_at": self._now(),
            "bootstrap_summary": {},
        }
        return self._load_json(self._path(simulation_id, "state.json"), default)

    def _save_state(self, simulation_id: str, state: Dict[str, Any]) -> None:
        state["updated_at"] = self._now()
        self._write_json(self._path(simulation_id, "state.json"), state)

    def _load_sources_index(self, simulation_id: str) -> Dict[str, Any]:
        default = {
            "simulation_id": simulation_id,
            "sources": [],
            "source_count": 0,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        return self._load_json(self._path(simulation_id, "sources_index.json"), default)

    def _save_sources_index(self, simulation_id: str, payload: Dict[str, Any]) -> None:
        payload["updated_at"] = self._now()
        self._write_json(self._path(simulation_id, "sources_index.json"), payload)

    def _manifest_path(self, simulation_id: str) -> str:
        return self._path(simulation_id, "manifest.json")

    def _ensure_manifest(self, simulation_id: str) -> Dict[str, Any]:
        manifest = self._load_json(self._manifest_path(simulation_id), {
            "simulation_id": simulation_id,
            "version": 1,
            "created_at": self._now(),
            "updated_at": self._now(),
            "files": {
                "state": "state.json",
                "sources_index": "sources_index.json",
                "claims": "claims.jsonl",
                "trials": "trials.jsonl",
                "agent_actions": "agent_actions.jsonl",
                "recalls": "recalls.jsonl",
                "relations": "relations.jsonl",
            },
        })
        self._write_json(self._manifest_path(simulation_id), manifest)
        return manifest

    def _reset_artifact_files(self, simulation_id: str) -> None:
        for filename in (
            "claims.jsonl",
            "trials.jsonl",
            "agent_actions.jsonl",
            "recalls.jsonl",
            "relations.jsonl",
            "sources_index.json",
            "simulation_config_snapshot.json",
            "profiles_snapshot.json",
            "state.json",
        ):
            path = self._path(simulation_id, filename)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _load_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        sim_dir = self._sim_dir(simulation_id)
        profiles: List[Dict[str, Any]] = []
        for filename in ("reddit_profiles.json", "twitter_profiles.csv"):
            path = os.path.join(sim_dir, filename)
            if not os.path.exists(path):
                continue
            try:
                if filename.endswith(".json"):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            profiles.extend([item for item in data if isinstance(item, dict)])
                else:
                    import csv

                    with open(path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        profiles.extend([dict(row) for row in reader])
            except Exception as exc:  # noqa: BLE001
                logger.warning("读取 profile 文件失败(%s): %s", filename, exc)
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            key = str(
                profile.get("user_id")
                or profile.get("agent_id")
                or profile.get("username")
                or profile.get("user_name")
                or profile.get("name")
                or uuid.uuid4().hex
            ).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(profile)
        return deduped

    def _load_simulation_config_snapshot(self, simulation_id: str) -> Dict[str, Any]:
        sim_dir = self._sim_dir(simulation_id)
        for filename in ("csi/simulation_config_snapshot.json", "simulation_config.json"):
            path = os.path.join(sim_dir, filename)
            if os.path.exists(path):
                data = self._load_json(path, {})
                if isinstance(data, dict):
                    return data
        return {}

    def _resolve_runtime_agent(
        self,
        simulation_id: str,
        agent_id: Optional[int] = None,
        agent_name: Optional[str] = None,
        agent_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = self._load_simulation_config_snapshot(simulation_id)
        profiles = self._load_profiles(simulation_id)
        roster = self._build_roster(config, profiles)

        resolved = None
        if agent_id is not None:
            for candidate in roster:
                if int(candidate.get("agent_id", -1)) == int(agent_id):
                    resolved = candidate
                    break

        if resolved is None and agent_name:
            needle = str(agent_name).strip().lower()
            for candidate in roster:
                name = str(candidate.get("agent_name") or candidate.get("entity_name") or "").strip().lower()
                if name and name == needle:
                    resolved = candidate
                    break

        if resolved is None and agent_context:
            resolved = dict(agent_context)

        resolved = resolved or {}
        merged = {
            "agent_id": agent_id if agent_id is not None else resolved.get("agent_id"),
            "agent_name": agent_name or resolved.get("agent_name") or resolved.get("entity_name") or "agent",
            "entity_uuid": resolved.get("entity_uuid") or (agent_context or {}).get("entity_uuid"),
            "entity_name": resolved.get("entity_name") or agent_name or "agent",
            "entity_type": resolved.get("entity_type") or "person",
            "role": resolved.get("role") or "general-investigator",
            "skills": resolved.get("skills") or [],
            "research_focus": resolved.get("research_focus") or [],
            "qualification_score": float(resolved.get("qualification_score", 0.75) or 0.75),
            "source_origin": resolved.get("source_origin") or "runtime",
            "source_priority": float(resolved.get("source_priority", 0.0) or 0.0),
            "entity_summary": resolved.get("entity_summary") or "",
            "bio": resolved.get("bio") or "",
            "persona": resolved.get("persona") or "",
        }
        if agent_context:
            for key, value in agent_context.items():
                if merged.get(key) in (None, "", [], {}):
                    merged[key] = value
        return merged

    def _extract_prompt_text(self, payload: Dict[str, Any]) -> str:
        prompt = payload.get("prompt") or payload.get("query") or payload.get("question")
        if isinstance(prompt, str) and prompt.strip():
            return prompt.strip()
        # For social actions, the "prompt" is the original content being responded to
        action_args = payload.get("action_args")
        if isinstance(action_args, dict):
            original = action_args.get("original_content") or action_args.get("post_content")
            if isinstance(original, str) and original.strip():
                return original.strip()
        return ""

    # ── Social action → CSI text extraction ──────────────────────

    _CONTENT_ACTIONS = {"CREATE_POST", "CREATE_COMMENT", "SEARCH_POSTS"}
    _REACTION_ACTIONS = {"LIKE_POST", "DISLIKE_POST", "UPVOTE_POST", "DOWNVOTE_POST"}
    _QUOTE_ACTIONS = {"QUOTE_POST", "REPOST"}
    _SKIP_ACTIONS = {"DO_NOTHING", "FOLLOW", "MUTE", "REFRESH"}

    def _extract_best_text(self, payload: Dict[str, Any]) -> str:
        """Extract the agent's own generated content from a social action."""
        action_type = str(payload.get("action_type", "")).upper()
        action_args = payload.get("action_args") or {}

        # 1) Agent's own content (posts, comments, search queries)
        if action_type in self._CONTENT_ACTIONS:
            content = action_args.get("content") or action_args.get("query")
            if isinstance(content, str) and content.strip():
                return content.strip()

        # 2) Quote posts: agent wrote a quote_content in response to original
        if action_type in self._QUOTE_ACTIONS:
            quote = action_args.get("quote_content") or action_args.get("content")
            if isinstance(quote, str) and quote.strip():
                return quote.strip()
            # Repost without commentary — use the original content
            original = action_args.get("original_content")
            if isinstance(original, str) and original.strip():
                return original.strip()

        # 3) Reactions (like/dislike): the "text" is the post they reacted to
        if action_type in self._REACTION_ACTIONS:
            reacted_to = action_args.get("post_content")
            if isinstance(reacted_to, str) and reacted_to.strip():
                return reacted_to.strip()

        # 4) Skip no-op actions
        if action_type in self._SKIP_ACTIONS:
            return ""

        # 5) Fallback: generic extraction for non-social payloads (interviews, etc.)
        candidates: List[Any] = [
            payload.get("response"),
            payload.get("content"),
            payload.get("text"),
            payload.get("result"),
        ]
        if isinstance(action_args, dict):
            candidates.extend([
                action_args.get("content"),
                action_args.get("text"),
                action_args.get("response"),
            ])
        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if isinstance(candidate, dict):
                for key in ("response", "answer", "content", "text", "summary"):
                    value = candidate.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return ""

    def _is_interaction_action(self, payload: Dict[str, Any]) -> bool:
        """Return True if this action is a response/reaction to another agent's content."""
        action_type = str(payload.get("action_type", "")).upper()
        return action_type in (
            self._QUOTE_ACTIONS | self._REACTION_ACTIONS | {"CREATE_COMMENT"}
        )

    def _extract_interaction_target(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the target agent and their content from an interaction action."""
        action_args = payload.get("action_args") or {}
        target_name = (
            action_args.get("original_author_name")
            or action_args.get("post_author_name")
            or ""
        )
        target_content = (
            action_args.get("original_content")
            or action_args.get("post_content")
            or ""
        )
        return {
            "target_agent_name": target_name,
            "target_content": target_content,
        }

    def _infer_verdict(self, text: str) -> str:
        lowered = (text or "").lower()
        if any(token in lowered for token in ("contradict", "inconsistent", "unsupported", "incorrect",
                                               "disagree", "wrong", "false", "misleading", "flawed")):
            return "contradicts"
        if any(token in lowered for token in ("uncertain", "needs revision", "revise", "not sure",
                                               "insufficient", "however", "but", "partially",
                                               "nuance", "caveat", "although")):
            return "needs_revision"
        return "supports"

    def _infer_verdict_from_action(self, action_type: str, text: str) -> str:
        """Infer verdict from the action type + content."""
        action_upper = action_type.upper()
        if action_upper in {"LIKE_POST", "UPVOTE_POST", "REPOST"}:
            return "supports"
        if action_upper in {"DISLIKE_POST", "DOWNVOTE_POST"}:
            return "contradicts"
        # For quotes and comments, infer from the text content
        return self._infer_verdict(text)

    def _infer_confidence(self, text: str, source_count: int, role: str = "") -> float:
        score = 0.58
        if source_count >= 1:
            score += 0.08
        if source_count >= 2:
            score += 0.08
        text_len = len((text or "").strip())
        if text_len > 180:
            score += 0.04
        if text_len > 400:
            score += 0.04
        if role.lower() in {"domain-analyst", "evidence-curator", "narrative-auditor",
                            "associationpresident", "domain participant"}:
            score += 0.05
        return max(0.25, min(score, 0.96))

    def advance_round_count(self, simulation_id: str, round_num: int, source: str = "runtime") -> int:
        with self._lock:
            state = self._load_state(simulation_id)
            current = int(state.get("round_count", 0) or 0)
            updated = max(current, int(round_num or 0))
            if updated > current:
                state["round_count"] = updated
                state["round_source"] = source
                self._save_state(simulation_id, state)
            return int(state.get("round_count", updated))

    def _normalize_profile(self, index: int, profile: Dict[str, Any], agent_cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        agent_id = int(profile.get("user_id") or profile.get("agent_id") or agent_cfg.get("agent_id") or index + 1)
        name = (
            profile.get("name")
            or profile.get("user_name")
            or profile.get("username")
            or agent_cfg.get("entity_name")
            or f"Agent {agent_id}"
        )
        role = profile.get("role") or agent_cfg.get("role") or profile.get("profession") or "general-investigator"
        skills = profile.get("skills") or agent_cfg.get("skills") or []
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]
        focus = profile.get("interested_topics") or agent_cfg.get("research_focus") or []
        if isinstance(focus, str):
            focus = [s.strip() for s in focus.split(",") if s.strip()]
        qualification = profile.get("qualification_score")
        if qualification is None:
            qualification = agent_cfg.get("qualification_score", 0.75)
        try:
            qualification = float(qualification)
        except Exception:  # noqa: BLE001
            qualification = 0.75

        return {
            "agent_id": agent_id,
            "agent_name": name,
            "entity_uuid": agent_cfg.get("entity_uuid") if agent_cfg else profile.get("source_entity_uuid"),
            "entity_name": agent_cfg.get("entity_name") if agent_cfg else name,
            "entity_type": agent_cfg.get("entity_type") if agent_cfg else profile.get("source_entity_type") or "person",
            "role": role,
            "skills": self._unique([str(s) for s in skills if str(s).strip()]),
            "research_focus": self._unique([str(s) for s in focus if str(s).strip()]),
            "qualification_score": max(0.0, min(qualification, 1.0)),
            "source_origin": agent_cfg.get("source_origin", "graph_entity") if agent_cfg else "profile",
            "source_priority": float(agent_cfg.get("source_priority", 0.0) if agent_cfg else 0.0),
            "entity_summary": agent_cfg.get("entity_summary", "") if agent_cfg else profile.get("bio", ""),
            "bio": profile.get("bio", ""),
            "persona": profile.get("persona", ""),
        }

    def _build_sources_index(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        simulation_config: Dict[str, Any],
        profiles: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        agent_cfgs = simulation_config.get("agent_configs", []) or []
        chunks = TextProcessor.split_text(TextProcessor.preprocess_text(document_text or ""), chunk_size=850, overlap=120)
        if not chunks and document_text.strip():
            chunks = [document_text.strip()]

        source_records: List[Dict[str, Any]] = []

        def add_source(source_type: str, title: str, content: str, origin: str, priority: float, metadata: Optional[Dict[str, Any]] = None):
            source_key = f"{source_type}:{title}:{content[:180]}"
            source_id = self._entity_id(simulation_id, "source", source_key)
            record = {
                "source_id": source_id,
                "source_type": source_type,
                "title": title,
                "summary": (content[:260] + "...") if len(content) > 260 else content,
                "content": content,
                "origin": origin,
                "priority": round(max(0.0, min(priority, 1.0)), 3),
                "keywords": self._unique(self._tokenize(f"{title} {content} {json.dumps(metadata or {}, ensure_ascii=False)}")),
                "metadata": metadata or {},
                "created_at": self._now(),
                "updated_at": self._now(),
            }
            source_records.append(record)

        requirement_title = simulation_requirement[:120] or "Simulation Requirement"
        add_source(
            "requirement",
            requirement_title,
            simulation_requirement or "",
            "project_requirement",
            1.0,
            {"simulation_id": simulation_id},
        )

        add_source(
            "document",
            "Document Corpus",
            document_text or "",
            "project_text",
            0.95,
            {"chunk_count": len(chunks)},
        )

        for idx, chunk in enumerate(chunks[:120]):
            add_source(
                "document_chunk",
                f"Chunk {idx + 1}",
                chunk,
                "project_text_chunk",
                0.9 - min(idx * 0.01, 0.2),
                {"chunk_index": idx + 1, "chunk_length": len(chunk)},
            )

        sources_index = {
            "simulation_id": simulation_id,
            "source_count": len(source_records),
            "sources": source_records,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._save_sources_index(simulation_id, sources_index)
        return sources_index

    def _agent_query_terms(self, agent: Dict[str, Any], simulation_requirement: str) -> List[str]:
        parts = [
            agent.get("role", ""),
            " ".join(agent.get("skills", []) or []),
            " ".join(agent.get("research_focus", []) or []),
            agent.get("entity_name", ""),
            agent.get("entity_type", ""),
            agent.get("entity_summary", ""),
            simulation_requirement or "",
        ]
        return self._tokenize(" ".join(parts))

    def _score_source(self, source: Dict[str, Any], query_terms: List[str]) -> float:
        haystack = " ".join([
            str(source.get("title", "")),
            str(source.get("summary", "")),
            str(source.get("content", "")),
            " ".join(source.get("keywords", []) or []),
        ]).lower()
        score = float(source.get("priority", 0.0) or 0.0)
        for term in query_terms:
            if term in haystack:
                score += 1.0
        if source.get("source_type") == "requirement":
            score += 1.25
        if source.get("source_type") == "document_chunk":
            score += 0.5
        return score

    def _select_sources(self, sources: List[Dict[str, Any]], query_terms: List[str], limit: int = 3) -> List[Dict[str, Any]]:
        ranked = sorted(
            sources,
            key=lambda src: self._score_source(src, query_terms),
            reverse=True,
        )
        return ranked[: max(1, limit)]

    def _draft_claim(self, agent: Dict[str, Any], sources: List[Dict[str, Any]], round_num: int) -> str:
        primary = sources[0] if sources else {}
        primary_title = primary.get("title", "input data")
        primary_summary = primary.get("summary", "") or primary.get("content", "")[:220]
        role = agent.get("role") or "investigator"
        name = agent.get("agent_name") or agent.get("entity_name") or f"Agent {agent.get('agent_id')}"
        if primary_summary:
            return f"{name} ({role}) infers that {primary_title} indicates: {primary_summary[:220]}"
        return f"{name} ({role}) proposes a claim for round {round_num} grounded in the available input data."

    def _peer_response(self, agent: Dict[str, Any], peer: Dict[str, Any], sources: List[Dict[str, Any]], claim_text: str) -> Tuple[str, str]:
        agent_terms = set(self._agent_query_terms(agent, claim_text))
        peer_terms = set(self._agent_query_terms(peer, claim_text))
        overlap = len(agent_terms & peer_terms)
        evidence_strength = sum(1 for src in sources if src.get("priority", 0) >= 0.8)
        if overlap >= 5 and evidence_strength >= 2:
            return "supports", "Peer review agrees that the claim is well grounded and sufficiently evidenced."
        if overlap >= 3:
            return "needs_revision", "Peer review requests tighter wording and stronger source linkage."
        return "contradicts", "Peer review flags the claim as under-evidenced or too broad."

    def _append_relation(
        self,
        simulation_id: str,
        relation_type: str,
        from_id: str,
        to_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        relation = {
            "relation_id": self._entity_id(simulation_id, "relation", f"{relation_type}:{from_id}:{to_id}:{json.dumps(metadata or {}, sort_keys=True)}"),
            "relation_type": relation_type,
            "from_id": from_id,
            "to_id": to_id,
            "metadata": metadata or {},
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._append_jsonl(self._path(simulation_id, "relations.jsonl"), relation)
        return relation

    def _append_agent_action(
        self,
        simulation_id: str,
        action_type: str,
        agent: Dict[str, Any],
        round_num: int,
        detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        action = {
            "action_id": self._entity_id(simulation_id, "action", f"{action_type}:{agent.get('agent_id')}:{round_num}:{json.dumps(detail, sort_keys=True)}"),
            "action_type": action_type,
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "round_num": round_num,
            "detail": detail,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._append_jsonl(self._path(simulation_id, "agent_actions.jsonl"), action)
        return action

    def _append_recall(
        self,
        simulation_id: str,
        agent: Dict[str, Any],
        round_num: int,
        query: str,
        selected_sources: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        recall = {
            "recall_id": self._entity_id(simulation_id, "recall", f"{agent.get('agent_id')}:{round_num}:{query[:80]}"),
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "query": query,
            "source_ids": [src.get("source_id") for src in selected_sources],
            "snippets": [
                {
                    "source_id": src.get("source_id"),
                    "title": src.get("title"),
                    "snippet": (src.get("summary") or src.get("content", ""))[:240],
                }
                for src in selected_sources
            ],
            "score": round(sum(src.get("priority", 0.0) for src in selected_sources), 3),
            "round_num": round_num,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._append_jsonl(self._path(simulation_id, "recalls.jsonl"), recall)
        return recall

    def _append_claim(
        self,
        simulation_id: str,
        agent: Dict[str, Any],
        round_num: int,
        claim_text: str,
        source_ids: List[str],
        confidence: float,
        status: str = "proposed",
        revision_of: Optional[str] = None,
    ) -> Dict[str, Any]:
        claim = {
            "claim_id": self._entity_id(simulation_id, "claim", f"{agent.get('agent_id')}:{round_num}:{claim_text[:120]}"),
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "entity_uuid": agent.get("entity_uuid"),
            "entity_name": agent.get("entity_name"),
            "entity_type": agent.get("entity_type"),
            "role": agent.get("role"),
            "text": claim_text,
            "source_ids": source_ids,
            "confidence": round(max(0.0, min(confidence, 1.0)), 3),
            "status": status,
            "round_num": round_num,
            "revision_of": revision_of,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._append_jsonl(self._path(simulation_id, "claims.jsonl"), claim)
        return claim

    def _append_trial(
        self,
        simulation_id: str,
        round_num: int,
        agent: Dict[str, Any],
        peer: Dict[str, Any],
        claim: Dict[str, Any],
        verdict: str,
        peer_response: str,
        selected_sources: List[Dict[str, Any]],
        trial_kind: str = "peer_review",
    ) -> Dict[str, Any]:
        trial = {
            "trial_id": self._entity_id(simulation_id, "trial", f"{agent.get('agent_id')}:{peer.get('agent_id')}:{round_num}:{claim.get('claim_id')}"),
            "trial_kind": trial_kind,
            "round_num": round_num,
            "query_agent_id": agent.get("agent_id"),
            "query_agent_name": agent.get("agent_name"),
            "target_agent_id": peer.get("agent_id"),
            "target_agent_name": peer.get("agent_name"),
            "claim_id": claim.get("claim_id"),
            "query": f"Please review and challenge the claim: {claim.get('text')}",
            "response": peer_response,
            "verdict": verdict,
            "source_ids": [src.get("source_id") for src in selected_sources],
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._append_jsonl(self._path(simulation_id, "trials.jsonl"), trial)
        return trial

    def record_runtime_action(self, simulation_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a runtime action and derive lightweight CSI artifacts."""
        with self._lock:
            agent = self._resolve_runtime_agent(
                simulation_id=simulation_id,
                agent_id=payload.get("agent_id"),
                agent_name=payload.get("agent_name"),
            )
            round_num = int(payload.get("round_num", payload.get("round", 0)) or 0)
            action_type = str(payload.get("action_type", "runtime_action"))
            detail = payload.get("detail")
            if not isinstance(detail, dict):
                detail = {}
            detail = {
                **detail,
                "platform": payload.get("platform"),
                "raw": payload,
            }

            action = self.record_agent_action(
                simulation_id,
                {
                    "action_type": action_type,
                    "agent_id": agent.get("agent_id"),
                    "agent_name": agent.get("agent_name"),
                    "entity_uuid": agent.get("entity_uuid"),
                    "entity_name": agent.get("entity_name"),
                    "entity_type": agent.get("entity_type"),
                    "role": agent.get("role"),
                    "round_num": round_num,
                    "detail": detail,
                },
            )

            prompt_text = self._extract_prompt_text(payload)
            query_text = prompt_text
            selected_sources = self._select_sources(
                self._load_sources_index(simulation_id).get("sources", []),
                self._tokenize(f"{query_text or action_type} {agent.get('role', '')} {agent.get('entity_summary', '')}"),
                limit=3,
            )
            source_ids = [src.get("source_id") for src in selected_sources if src.get("source_id")]

            bundle: Dict[str, Any] = {
                "action": action,
                "claim": None,
                "trial": None,
                "recall": None,
                "relations": [],
            }

            text = self._extract_best_text(payload)
            if query_text or text or action_type.upper() not in self._SKIP_ACTIONS:
                recall_query = query_text or (text[:240] if text else action_type)
                recall = self.record_recall(
                    simulation_id,
                    {
                        "agent_id": agent.get("agent_id"),
                        "agent_name": agent.get("agent_name"),
                        "query": recall_query,
                        "source_ids": source_ids,
                        "snippets": [
                            {
                                "source_id": src.get("source_id"),
                                "title": src.get("title"),
                                "snippet": (src.get("summary") or src.get("content", ""))[:240],
                            }
                            for src in selected_sources
                        ],
                        "score": sum(float(src.get("priority", 0.0) or 0.0) for src in selected_sources),
                        "round_num": round_num,
                    },
                )
                bundle["recall"] = recall

            # ── Create claim from content-producing actions ────────────
            action_upper = action_type.upper()
            is_content_action = action_upper not in self._SKIP_ACTIONS
            is_interaction = self._is_interaction_action(payload)

            if text and is_content_action:
                confidence = self._infer_confidence(text, len(selected_sources), str(agent.get("role", "")))

                # For reactions (like/dislike), the text is the *target's* content.
                # We don't create a new claim — we create a trial referencing it.
                if action_upper in self._REACTION_ACTIONS:
                    # Reactions produce trials, not claims.
                    pass
                else:
                    claim = self.record_claim(
                        simulation_id,
                        {
                            "agent_id": agent.get("agent_id"),
                            "agent_name": agent.get("agent_name"),
                            "entity_uuid": agent.get("entity_uuid"),
                            "entity_name": agent.get("entity_name"),
                            "entity_type": agent.get("entity_type"),
                            "role": agent.get("role"),
                            "text": text,
                            "source_ids": source_ids,
                            "confidence": confidence,
                            "status": payload.get("claim_status", "proposed"),
                            "round_num": round_num,
                        },
                    )
                    bundle["claim"] = claim

                    if source_ids:
                        bundle["relations"].append(
                            self.record_relation(
                                simulation_id,
                                {
                                    "relation_type": "derived_from",
                                    "from_id": claim["claim_id"],
                                    "to_id": source_ids[0],
                                    "metadata": {"round_num": round_num, "action_id": action["action_id"]},
                                },
                            )
                        )

                # ── Create trial from interactions (quotes, comments, reactions) ──
                interaction_info = self._extract_interaction_target(payload) if is_interaction else {}
                target_agent_name = (
                    payload.get("target_agent_name")
                    or interaction_info.get("target_agent_name")
                    or ""
                )
                target_agent_id = payload.get("target_agent_id")
                target_content = interaction_info.get("target_content", "")

                should_create_trial = (
                    payload.get("force_trial")
                    or is_interaction
                    or target_agent_id is not None
                    or target_agent_name
                )

                if should_create_trial:
                    verdict = self._infer_verdict_from_action(action_type, text)

                    # For reactions, we record what they reacted to as the query
                    trial_query = target_content or query_text or text[:240]
                    trial_response = text if action_upper not in self._REACTION_ACTIONS else action_upper.lower()
                    trial_claim_id = bundle["claim"]["claim_id"] if bundle["claim"] else None

                    # Determine trial kind based on action type
                    if action_upper in self._REACTION_ACTIONS:
                        trial_kind = "reaction"
                    elif action_upper in self._QUOTE_ACTIONS:
                        trial_kind = "quote_response"
                    elif action_upper == "CREATE_COMMENT":
                        trial_kind = "comment_response"
                    else:
                        trial_kind = payload.get("trial_kind", "runtime")

                    trial = self.record_trial(
                        simulation_id,
                        {
                            "round_num": round_num,
                            "query_agent_id": agent.get("agent_id"),
                            "query_agent_name": agent.get("agent_name"),
                            "target_agent_id": target_agent_id,
                            "target_agent_name": target_agent_name,
                            "claim_id": trial_claim_id,
                            "query": trial_query,
                            "response": trial_response,
                            "verdict": verdict,
                            "source_ids": source_ids,
                            "trial_kind": trial_kind,
                        },
                    )
                    bundle["trial"] = trial

                    # Link trial to the claim it's evaluating
                    link_target = trial_claim_id
                    if link_target:
                        bundle["relations"].append(
                            self.record_relation(
                                simulation_id,
                                {
                                    "relation_type": verdict if verdict in {"supports", "contradicts"} else "updates",
                                    "from_id": trial["trial_id"],
                                    "to_id": link_target,
                                    "metadata": {
                                        "round_num": round_num,
                                        "action_id": action["action_id"],
                                        "trial_kind": trial_kind,
                                    },
                                },
                            )
                        )

            if round_num:
                self.advance_round_count(simulation_id, round_num, source="runtime_action")

            return bundle

    def record_runtime_interview(self, simulation_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Persist an interview turn and derive claims/trials/recalls."""
        interview_payload = dict(payload)
        interview_payload.setdefault("action_type", "interview")
        interview_payload.setdefault("trial_kind", "interview")
        interview_payload.setdefault("claim_status", "interview_response")
        interview_payload.setdefault("force_trial", True)
        interview_payload.setdefault("target_agent_name", interview_payload.get("target_agent_name") or "user")
        return self.record_runtime_action(simulation_id, interview_payload)

    def _build_roster(
        self,
        simulation_config: Dict[str, Any],
        profiles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        agent_cfgs = simulation_config.get("agent_configs", []) or []
        profile_by_name = {}
        profile_by_id = {}
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            name = str(profile.get("name") or profile.get("user_name") or profile.get("username") or "").strip().lower()
            if name:
                profile_by_name[name] = profile
            uid = profile.get("user_id") or profile.get("agent_id")
            if uid is not None:
                profile_by_id[str(uid)] = profile

        roster = []
        for index, agent_cfg in enumerate(agent_cfgs):
            profile = profile_by_id.get(str(agent_cfg.get("agent_id")))
            if profile is None:
                lookup_name = str(agent_cfg.get("entity_name") or "").strip().lower()
                profile = profile_by_name.get(lookup_name)
            if profile is None and index < len(profiles):
                profile = profiles[index]
            profile = profile if isinstance(profile, dict) else {}
            roster.append(self._normalize_profile(index, profile, agent_cfg))
        return roster

    def _run_working_rounds(
        self,
        simulation_id: str,
        simulation_requirement: str,
        roster: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        rounds: int = 1,
        preferred_target_agent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        claim_count = 0
        trial_count = 0
        action_count = 0
        recall_count = 0
        relation_count = 0
        generated_claims: List[Dict[str, Any]] = []
        generated_trials: List[Dict[str, Any]] = []
        generated_actions: List[Dict[str, Any]] = []
        generated_recalls: List[Dict[str, Any]] = []
        generated_relations: List[Dict[str, Any]] = []

        if not roster or not sources:
            return {
                "rounds": 0,
                "claims": 0,
                "trials": 0,
                "agent_actions": 0,
                "recalls": 0,
                "relations": 0,
                "generated_claims": [],
                "generated_trials": [],
            }

        for round_index in range(rounds):
            round_num = round_index + 1
            for idx, agent in enumerate(roster):
                query_terms = self._agent_query_terms(agent, simulation_requirement)
                selected_sources = self._select_sources(sources, query_terms, limit=3)
                recall = self._append_recall(
                    simulation_id=simulation_id,
                    agent=agent,
                    round_num=round_num,
                    query=" ".join(query_terms)[:240],
                    selected_sources=selected_sources,
                )
                generated_recalls.append(recall)
                recall_count += 1
                generated_actions.append(
                    self._append_agent_action(
                        simulation_id=simulation_id,
                        action_type="recall",
                        agent=agent,
                        round_num=round_num,
                        detail={"recall_id": recall["recall_id"], "source_ids": recall["source_ids"]},
                    )
                )
                action_count += 1

                claim_text = self._draft_claim(agent, selected_sources, round_num)
                claim = self._append_claim(
                    simulation_id=simulation_id,
                    agent=agent,
                    round_num=round_num,
                    claim_text=claim_text,
                    source_ids=[src.get("source_id") for src in selected_sources],
                    confidence=0.72 + min(agent.get("qualification_score", 0.0), 0.2),
                )
                generated_claims.append(claim)
                claim_count += 1
                generated_actions.append(
                    self._append_agent_action(
                        simulation_id=simulation_id,
                        action_type="claim_propose",
                        agent=agent,
                        round_num=round_num,
                        detail={"claim_id": claim["claim_id"], "source_ids": claim["source_ids"]},
                    )
                )
                action_count += 1

                self._append_relation(
                    simulation_id=simulation_id,
                    relation_type="derived_from",
                    from_id=claim["claim_id"],
                    to_id=selected_sources[0]["source_id"] if selected_sources else "source:unknown",
                    metadata={"round_num": round_num, "agent_id": agent.get("agent_id")},
                )
                relation_count += 1
                generated_relations.append({
                    "relation_type": "derived_from",
                    "from_id": claim["claim_id"],
                    "to_id": selected_sources[0]["source_id"] if selected_sources else "source:unknown",
                })

                if preferred_target_agent_id is not None:
                    peer = next(
                        (candidate for candidate in roster if candidate.get("agent_id") == preferred_target_agent_id),
                        roster[(idx + 1) % len(roster)],
                    )
                else:
                    peer = roster[(idx + 1) % len(roster)]
                if peer.get("agent_id") == agent.get("agent_id") and len(roster) > 1:
                    peer = roster[(idx + 1) % len(roster)]
                verdict, peer_response = self._peer_response(agent, peer, selected_sources, claim_text)
                trial = self._append_trial(
                    simulation_id=simulation_id,
                    round_num=round_num,
                    agent=agent,
                    peer=peer,
                    claim=claim,
                    verdict=verdict,
                    peer_response=peer_response,
                    selected_sources=selected_sources,
                )
                generated_trials.append(trial)
                trial_count += 1
                generated_actions.append(
                    self._append_agent_action(
                        simulation_id=simulation_id,
                        action_type="query_peer",
                        agent=agent,
                        round_num=round_num,
                        detail={
                            "trial_id": trial["trial_id"],
                            "target_agent_id": peer.get("agent_id"),
                            "verdict": verdict,
                        },
                    )
                )
                action_count += 1

                relation_type = "supports" if verdict == "supports" else "contradicts"
                self._append_relation(
                    simulation_id=simulation_id,
                    relation_type=relation_type,
                    from_id=trial["trial_id"],
                    to_id=claim["claim_id"],
                    metadata={"peer_id": peer.get("agent_id"), "round_num": round_num},
                )
                relation_count += 1
                generated_relations.append({
                    "relation_type": relation_type,
                    "from_id": trial["trial_id"],
                    "to_id": claim["claim_id"],
                })

                if verdict != "supports":
                    revised_text = (
                        f"{claim_text} Peer review by {peer.get('agent_name')} requested revision: {peer_response}"
                    )
                    revised_claim = self._append_claim(
                        simulation_id=simulation_id,
                        agent=agent,
                        round_num=round_num,
                        claim_text=revised_text,
                        source_ids=claim["source_ids"],
                        confidence=max(0.55, claim["confidence"] - 0.1),
                        status="revised",
                        revision_of=claim["claim_id"],
                    )
                    generated_claims.append(revised_claim)
                    claim_count += 1
                    generated_actions.append(
                        self._append_agent_action(
                            simulation_id=simulation_id,
                            action_type="revise_claim",
                            agent=agent,
                            round_num=round_num,
                            detail={"claim_id": revised_claim["claim_id"], "revision_of": claim["claim_id"]},
                        )
                    )
                    action_count += 1
                    self._append_relation(
                        simulation_id=simulation_id,
                        relation_type="updates",
                        from_id=revised_claim["claim_id"],
                        to_id=claim["claim_id"],
                        metadata={"round_num": round_num, "peer_id": peer.get("agent_id")},
                    )
                    relation_count += 1
                    generated_relations.append({
                        "relation_type": "updates",
                        "from_id": revised_claim["claim_id"],
                        "to_id": claim["claim_id"],
                    })

        return {
            "rounds": rounds,
            "claims": claim_count,
            "trials": trial_count,
            "agent_actions": action_count,
            "recalls": recall_count,
            "relations": relation_count,
            "generated_claims": generated_claims,
            "generated_trials": generated_trials,
            "generated_actions": generated_actions,
            "generated_recalls": generated_recalls,
            "generated_relations": generated_relations,
        }

    def initialize_from_prepare(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        simulation_config: Dict[str, Any],
        profiles: List[Dict[str, Any]],
        bootstrap_rounds: int = 1,
    ) -> Dict[str, Any]:
        """Build the local CSI working set from prepare artifacts."""
        with self._lock:
            self._csi_dir(simulation_id)
            self._reset_artifact_files(simulation_id)
            self._ensure_manifest(simulation_id)
            self._write_json(self._path(simulation_id, "simulation_config_snapshot.json"), simulation_config)
            self._write_json(self._path(simulation_id, "profiles_snapshot.json"), profiles)

            sources_index = self._build_sources_index(
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                simulation_config=simulation_config,
                profiles=profiles,
            )
            roster = self._build_roster(simulation_config, profiles)

            # Run template bootstrap rounds (0 = skip entirely)
            effective_rounds = max(0, int(bootstrap_rounds))
            if effective_rounds > 0:
                bootstrap = self._run_working_rounds(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    roster=roster[:25],
                    sources=sources_index.get("sources", []),
                    rounds=effective_rounds,
                )
            else:
                bootstrap = {
                    "rounds": 0, "claims": 0, "trials": 0,
                    "agent_actions": 0, "recalls": 0, "relations": 0,
                    "generated_claims": [], "generated_trials": [],
                }

            state = self._load_state(simulation_id)
            state.update({
                "simulation_id": simulation_id,
                "project_id": project_id,
                "graph_id": graph_id,
                "initialized": True,
                "round_count": max(int(state.get("round_count", 0)), int(bootstrap.get("rounds", 0))),
                "source_count": sources_index.get("source_count", 0),
                "claim_count": bootstrap.get("claims", 0),
                "trial_count": bootstrap.get("trials", 0),
                "agent_action_count": bootstrap.get("agent_actions", 0),
                "recall_count": bootstrap.get("recalls", 0),
                "relation_count": bootstrap.get("relations", 0),
                "bootstrap_summary": {
                    "agents": len(roster),
                    "bootstrap_rounds": bootstrap.get("rounds", 0),
                    "sources_index_path": "sources_index.json",
                },
            })
            self._save_state(simulation_id, state)

            manifest = self._ensure_manifest(simulation_id)
            manifest["updated_at"] = self._now()
            manifest["source_count"] = sources_index.get("source_count", 0)
            manifest["claim_count"] = bootstrap.get("claims", 0)
            manifest["trial_count"] = bootstrap.get("trials", 0)
            manifest["agent_action_count"] = bootstrap.get("agent_actions", 0)
            manifest["recall_count"] = bootstrap.get("recalls", 0)
            manifest["relation_count"] = bootstrap.get("relations", 0)
            self._write_json(self._manifest_path(simulation_id), manifest)

            return {
                "simulation_id": simulation_id,
                "project_id": project_id,
                "graph_id": graph_id,
                "state": state,
                "manifest": manifest,
                "sources_index": sources_index,
                "bootstrap": bootstrap,
            }

    def record_claim(self, simulation_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            record = {
                "claim_id": payload.get("claim_id") or self._entity_id(simulation_id, "claim", uuid.uuid4().hex),
                "agent_id": payload.get("agent_id"),
                "agent_name": payload.get("agent_name"),
                "entity_uuid": payload.get("entity_uuid"),
                "entity_name": payload.get("entity_name"),
                "entity_type": payload.get("entity_type"),
                "role": payload.get("role"),
                "text": payload.get("text") or payload.get("claim") or "",
                "source_ids": payload.get("source_ids") or [],
                "confidence": round(float(payload.get("confidence", 0.5)), 3),
                "status": payload.get("status", "proposed"),
                "round_num": int(payload.get("round_num", 0) or 0),
                "revision_of": payload.get("revision_of"),
                "created_at": self._now(),
                "updated_at": self._now(),
            }
            self._append_jsonl(self._path(simulation_id, "claims.jsonl"), record)
            state = self._load_state(simulation_id)
            state["claim_count"] = int(state.get("claim_count", 0)) + 1
            self._save_state(simulation_id, state)
            return record

    def record_trial(self, simulation_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            record = {
                "trial_id": payload.get("trial_id") or self._entity_id(simulation_id, "trial", uuid.uuid4().hex),
                "trial_kind": payload.get("trial_kind", "peer_review"),
                "round_num": int(payload.get("round_num", 0) or 0),
                "query_agent_id": payload.get("query_agent_id"),
                "query_agent_name": payload.get("query_agent_name"),
                "target_agent_id": payload.get("target_agent_id"),
                "target_agent_name": payload.get("target_agent_name"),
                "claim_id": payload.get("claim_id"),
                "query": payload.get("query", ""),
                "response": payload.get("response", ""),
                "verdict": payload.get("verdict", "needs_revision"),
                "source_ids": payload.get("source_ids") or [],
                "created_at": self._now(),
                "updated_at": self._now(),
            }
            self._append_jsonl(self._path(simulation_id, "trials.jsonl"), record)
            state = self._load_state(simulation_id)
            state["trial_count"] = int(state.get("trial_count", 0)) + 1
            self._save_state(simulation_id, state)
            return record

    def record_agent_action(self, simulation_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            record = {
                "action_id": payload.get("action_id") or self._entity_id(simulation_id, "action", uuid.uuid4().hex),
                "action_type": payload.get("action_type", "observe"),
                "agent_id": payload.get("agent_id"),
                "agent_name": payload.get("agent_name"),
                "entity_uuid": payload.get("entity_uuid"),
                "entity_name": payload.get("entity_name"),
                "entity_type": payload.get("entity_type"),
                "role": payload.get("role"),
                "round_num": int(payload.get("round_num", 0) or 0),
                "detail": payload.get("detail") or {},
                "created_at": self._now(),
                "updated_at": self._now(),
            }
            self._append_jsonl(self._path(simulation_id, "agent_actions.jsonl"), record)
            state = self._load_state(simulation_id)
            state["agent_action_count"] = int(state.get("agent_action_count", 0)) + 1
            self._save_state(simulation_id, state)
            return record

    def record_recall(self, simulation_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            record = {
                "recall_id": payload.get("recall_id") or self._entity_id(simulation_id, "recall", uuid.uuid4().hex),
                "agent_id": payload.get("agent_id"),
                "agent_name": payload.get("agent_name"),
                "query": payload.get("query", ""),
                "source_ids": payload.get("source_ids") or [],
                "snippets": payload.get("snippets") or [],
                "score": round(float(payload.get("score", 0.0)), 3),
                "round_num": int(payload.get("round_num", 0) or 0),
                "created_at": self._now(),
                "updated_at": self._now(),
            }
            self._append_jsonl(self._path(simulation_id, "recalls.jsonl"), record)
            state = self._load_state(simulation_id)
            state["recall_count"] = int(state.get("recall_count", 0)) + 1
            self._save_state(simulation_id, state)
            return record

    def record_relation(self, simulation_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            relation = {
                "relation_id": payload.get("relation_id") or self._entity_id(
                    simulation_id,
                    "relation",
                    uuid.uuid4().hex,
                ),
                "relation_type": payload.get("relation_type", "updates"),
                "from_id": payload.get("from_id"),
                "to_id": payload.get("to_id"),
                "metadata": payload.get("metadata") or {},
                "created_at": self._now(),
                "updated_at": self._now(),
            }
            self._append_jsonl(self._path(simulation_id, "relations.jsonl"), relation)
            state = self._load_state(simulation_id)
            state["relation_count"] = int(state.get("relation_count", 0)) + 1
            self._save_state(simulation_id, state)
            return relation

    def run_local_rounds(
        self,
        simulation_id: str,
        simulation_requirement: str,
        rounds: int = 1,
        preferred_target_agent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            simulation_config = self._load_json(self._path(simulation_id, "simulation_config_snapshot.json"), {})
            if not simulation_config:
                simulation_config = self._load_json(
                    os.path.join(self._sim_dir(simulation_id), "simulation_config.json"),
                    {},
                )
            profiles = self._load_profiles(simulation_id)
            sources_index = self._load_sources_index(simulation_id)
            roster = self._build_roster(simulation_config, profiles)
            result = self._run_working_rounds(
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                roster=roster,
                sources=sources_index.get("sources", []),
                rounds=max(1, int(rounds)),
                preferred_target_agent_id=preferred_target_agent_id,
            )

            state = self._load_state(simulation_id)
            state["round_count"] = int(state.get("round_count", 0)) + max(1, int(rounds))
            state["claim_count"] = int(state.get("claim_count", 0)) + result.get("claims", 0)
            state["trial_count"] = int(state.get("trial_count", 0)) + result.get("trials", 0)
            state["agent_action_count"] = int(state.get("agent_action_count", 0)) + result.get("agent_actions", 0)
            state["recall_count"] = int(state.get("recall_count", 0)) + result.get("recalls", 0)
            state["relation_count"] = int(state.get("relation_count", 0)) + result.get("relations", 0)
            self._save_state(simulation_id, state)
            return {
                "simulation_id": simulation_id,
                "state": state,
                "result": result,
            }

    def get_state(self, simulation_id: str) -> Dict[str, Any]:
        return self._load_state(simulation_id)

    def has_artifacts(self, simulation_id: str) -> bool:
        """Return True when the simulation has local CSI artifacts on disk."""
        return os.path.exists(self._path(simulation_id, "state.json"))

    def get_snapshot(self, simulation_id: str) -> Dict[str, Any]:
        state = self._load_state(simulation_id)
        sources = self._load_sources_index(simulation_id)
        claims = self._read_jsonl(self._path(simulation_id, "claims.jsonl"))
        trials = self._read_jsonl(self._path(simulation_id, "trials.jsonl"))
        actions = self._read_jsonl(self._path(simulation_id, "agent_actions.jsonl"))
        recalls = self._read_jsonl(self._path(simulation_id, "recalls.jsonl"))
        relations = self._read_jsonl(self._path(simulation_id, "relations.jsonl"))

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        for source in sources.get("sources", []):
            nodes.append({
                "id": source.get("source_id"),
                "type": source.get("source_type"),
                "label": source.get("title"),
                "summary": source.get("summary"),
                "content": source.get("content"),
                "metadata": source.get("metadata", {}),
                "origin": source.get("origin"),
            })

        for claim in claims:
            nodes.append({
                "id": claim.get("claim_id"),
                "type": "claim",
                "label": claim.get("text", "")[:120],
                "summary": claim.get("text"),
                "metadata": claim,
            })

        for trial in trials:
            nodes.append({
                "id": trial.get("trial_id"),
                "type": "trial",
                "label": trial.get("verdict", "trial"),
                "summary": trial.get("response"),
                "metadata": trial,
            })

        for action in actions:
            nodes.append({
                "id": action.get("action_id"),
                "type": "agent_action",
                "label": action.get("action_type"),
                "summary": json.dumps(action.get("detail", {}), ensure_ascii=False)[:200],
                "metadata": action,
            })

        for recall in recalls:
            nodes.append({
                "id": recall.get("recall_id"),
                "type": "recall",
                "label": recall.get("query", "")[:120],
                "summary": "; ".join([snippet.get("snippet", "") for snippet in recall.get("snippets", [])[:2]]),
                "metadata": recall,
            })

        for relation in relations:
            edges.append({
                "id": relation.get("relation_id"),
                "type": relation.get("relation_type"),
                "source": relation.get("from_id"),
                "target": relation.get("to_id"),
                "metadata": relation.get("metadata", {}),
            })

        return {
            "state": state,
            "manifest": self._load_json(self._manifest_path(simulation_id), {}),
            "profiles": self._load_profiles(simulation_id),
            "sources_index": sources,
            "claims": claims,
            "trials": trials,
            "agent_actions": actions,
            "recalls": recalls,
            "relations": relations,
            "nodes": nodes,
            "edges": edges,
            "counts": {
                "sources": len(sources.get("sources", [])),
                "claims": len(claims),
                "trials": len(trials),
                "agent_actions": len(actions),
                "recalls": len(recalls),
                "relations": len(relations),
            },
        }
