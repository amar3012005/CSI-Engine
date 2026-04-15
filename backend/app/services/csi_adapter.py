"""
CSI Adapter

统一封装 CSI 实体/关系/报告溯源的持久化逻辑：
1) GRAPH_PROVIDER=hivemind 时，优先尝试写入 HIVEMIND HTTP API
2) 本地 uploads/csi 维护派生镜像，用于快速读取/回放
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from ..config import Config
from ..utils.logger import get_logger


CANONICAL_ENTITY_TYPES = {
    "source",
    "extract",
    "claim",
    "verdict",
    "trail",
    "blueprint",
    "agentaction",
}

CANONICAL_RELATION_TYPES = {
    "supports",
    "contradicts",
    "derived_from",
    "updates",
    "used_in_report",
}


class CSIAdapter:
    """CSI 数据适配层（API 无关，可被 route/service 直接调用）。"""

    def __init__(self):
        self.provider = Config.GRAPH_PROVIDER
        self.hivemind_api_url = (Config.HIVEMIND_API_URL or "").rstrip("/")
        self.hivemind_api_key = Config.HIVEMIND_API_KEY
        self.logger = get_logger("mirofish.csi_adapter")
        self._lock = threading.Lock()

    @property
    def _csi_dir(self) -> str:
        path = os.path.join(Config.UPLOAD_FOLDER, "csi")
        os.makedirs(path, exist_ok=True)
        return path

    def _project_cache_file(self, project_id: str) -> str:
        return os.path.join(self._csi_dir, f"{project_id}.json")

    def _now(self) -> str:
        return datetime.now().isoformat()

    def _normalize_type(self, value: str) -> str:
        return (value or "").strip().lower().replace("_", "")

    def _validate_entity_type(self, entity_type: str) -> str:
        normalized = self._normalize_type(entity_type)
        if normalized not in CANONICAL_ENTITY_TYPES:
            raise ValueError(f"不支持的实体类型: {entity_type}")
        return normalized

    def _validate_relation_type(self, relation_type: str) -> str:
        normalized = (relation_type or "").strip().lower()
        if normalized not in CANONICAL_RELATION_TYPES:
            raise ValueError(f"不支持的关系类型: {relation_type}")
        return normalized

    def _stable_hash(self, payload: Dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _entity_id(
        self,
        project_id: str,
        entity_type: str,
        key: Optional[str],
        attributes: Optional[Dict[str, Any]],
        explicit_id: Optional[str] = None,
    ) -> str:
        if explicit_id:
            return explicit_id
        normalized_type = self._validate_entity_type(entity_type)
        canonical_payload = {
            "project_id": project_id,
            "entity_type": normalized_type,
            "key": key or "",
            "attributes": attributes or {},
        }
        digest = self._stable_hash(canonical_payload)[:24]
        return f"csi_{normalized_type}_{digest}"

    def _relation_id(
        self,
        project_id: str,
        relation_type: str,
        from_entity_id: str,
        to_entity_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        normalized_type = self._validate_relation_type(relation_type)
        canonical_payload = {
            "project_id": project_id,
            "relation_type": normalized_type,
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "metadata": metadata or {},
        }
        digest = self._stable_hash(canonical_payload)[:24]
        return f"csi_rel_{digest}"

    def _provenance_id(self, project_id: str, report_id: str) -> str:
        digest = self._stable_hash({"project_id": project_id, "report_id": report_id})[:24]
        return f"csi_prov_{digest}"

    def _load_project_cache(self, project_id: str) -> Dict[str, Any]:
        path = self._project_cache_file(project_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "project_id": project_id,
            "entities": {},
            "relations": {},
            "provenance": {},
            "created_at": self._now(),
            "updated_at": self._now(),
            "version": 1,
        }

    def _save_project_cache(self, project_id: str, cache_data: Dict[str, Any]) -> None:
        cache_data["updated_at"] = self._now()
        path = self._project_cache_file(project_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

    def _hivemind_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-Key": self.hivemind_api_key or "",
            "Authorization": f"Bearer {self.hivemind_api_key or ''}",
        }

    def _hivemind_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 8.0,
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        if self.provider != "hivemind":
            return False, None, "GRAPH_PROVIDER 非 hivemind，跳过远端写入"
        if not self.hivemind_api_url or not self.hivemind_api_key:
            return False, None, "HIVEMIND 配置不完整"

        url = f"{self.hivemind_api_url}{endpoint}"
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = urlrequest.Request(
            url=url,
            data=body if method.upper() in {"POST", "PUT", "PATCH"} else None,
            headers=self._hivemind_headers(),
            method=method.upper(),
        )
        try:
            with urlrequest.urlopen(request, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return True, json.loads(raw) if raw else {}, None
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            err = f"HIVEMIND HTTP {e.code}: {detail[:240]}"
            self.logger.warning(err)
            return False, None, err
        except URLError as e:
            err = f"HIVEMIND 不可达: {e.reason}"
            self.logger.warning(err)
            return False, None, err
        except Exception as e:  # noqa: BLE001
            err = f"HIVEMIND 请求异常: {e}"
            self.logger.warning(err)
            return False, None, err

    def _mirror_entity(self, project_id: str, entity: Dict[str, Any]) -> None:
        with self._lock:
            cache = self._load_project_cache(project_id)
            cache["entities"][entity["entity_id"]] = entity
            self._save_project_cache(project_id, cache)

    def _mirror_relation(self, project_id: str, relation: Dict[str, Any]) -> None:
        with self._lock:
            cache = self._load_project_cache(project_id)
            cache["relations"][relation["relation_id"]] = relation
            self._save_project_cache(project_id, cache)

    def _mirror_provenance(self, project_id: str, provenance: Dict[str, Any]) -> None:
        with self._lock:
            cache = self._load_project_cache(project_id)
            cache["provenance"][provenance["report_id"]] = provenance
            self._save_project_cache(project_id, cache)

    def upsert_entity(
        self,
        project_id: str,
        entity_type: str,
        key: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        entity_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Upsert CSI 实体（本地镜像必写，HIVEMIND 远端最佳努力写入）。
        """
        normalized_type = self._validate_entity_type(entity_type)
        canonical_id = self._entity_id(project_id, normalized_type, key, attributes, explicit_id=entity_id)
        now = self._now()

        entity = {
            "entity_id": canonical_id,
            "project_id": project_id,
            "entity_type": normalized_type,
            "key": key,
            "attributes": attributes or {},
            "metadata": metadata or {},
            "updated_at": now,
            "created_at": now,
        }

        # 尝试保留已有 created_at
        with self._lock:
            cache = self._load_project_cache(project_id)
            existing = cache["entities"].get(canonical_id)
            if existing:
                entity["created_at"] = existing.get("created_at", now)
            cache["entities"][canonical_id] = entity
            self._save_project_cache(project_id, cache)

        remote_ok = False
        remote_error = None
        remote_response = None
        if self.provider == "hivemind":
            payload = {
                "title": f"CSI::{normalized_type}::{key or canonical_id}",
                "content": json.dumps(entity, ensure_ascii=False),
                "source_type": "decision",
                "tags": ["csi", f"csi:{normalized_type}", f"project:{project_id}", "mirofish"],
                "project": f"mirofish-csi-{project_id}",
            }
            # 使用已存在的 /api/memories 作为通用写入入口
            remote_ok, remote_response, remote_error = self._hivemind_request("POST", "/api/memories", payload)

        return {
            "ok": True,
            "entity": entity,
            "remote_synced": remote_ok,
            "remote_error": remote_error,
            "remote_response": remote_response,
        }

    def create_relation(
        self,
        project_id: str,
        relation_type: str,
        from_entity_id: str,
        to_entity_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        relation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建实体关系（supports/contradicts/derived_from/updates/used_in_report）。
        """
        normalized_type = self._validate_relation_type(relation_type)
        rid = relation_id or self._relation_id(
            project_id=project_id,
            relation_type=normalized_type,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            metadata=metadata,
        )
        now = self._now()
        relation = {
            "relation_id": rid,
            "project_id": project_id,
            "relation_type": normalized_type,
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }

        self._mirror_relation(project_id, relation)

        remote_ok = False
        remote_error = None
        remote_response = None
        if self.provider == "hivemind":
            payload = {
                "title": f"CSI::relation::{normalized_type}",
                "content": json.dumps(relation, ensure_ascii=False),
                "source_type": "decision",
                "tags": ["csi", "csi:relation", f"relation:{normalized_type}", f"project:{project_id}", "mirofish"],
                "project": f"mirofish-csi-{project_id}",
            }
            remote_ok, remote_response, remote_error = self._hivemind_request("POST", "/api/memories", payload)

        return {
            "ok": True,
            "relation": relation,
            "remote_synced": remote_ok,
            "remote_error": remote_error,
            "remote_response": remote_response,
        }

    def persist_report_provenance(
        self,
        project_id: str,
        report_id: Optional[str],
        report_title: str,
        node_ids: List[str],
        relation_ids: List[str],
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        持久化报告溯源（golden line）。
        """
        resolved_report_id = report_id or f"report_{uuid.uuid4().hex[:12]}"
        provenance_id = self._provenance_id(project_id, resolved_report_id)
        now = self._now()

        record = {
            "provenance_id": provenance_id,
            "project_id": project_id,
            "report_id": resolved_report_id,
            "report_title": report_title,
            "summary": summary or "",
            "node_ids": sorted(set(node_ids)),
            "relation_ids": sorted(set(relation_ids)),
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }

        self._mirror_provenance(project_id, record)

        # 同步 used_in_report 关系，便于统一查询
        relation_results = []
        for node_id in record["node_ids"]:
            relation_results.append(
                self.create_relation(
                    project_id=project_id,
                    relation_type="used_in_report",
                    from_entity_id=node_id,
                    to_entity_id=resolved_report_id,
                    metadata={"provenance_id": provenance_id},
                )
            )

        remote_ok = False
        remote_error = None
        remote_response = None
        if self.provider == "hivemind":
            payload = {
                "title": f"CSI::provenance::{resolved_report_id}",
                "content": json.dumps(record, ensure_ascii=False),
                "source_type": "documentation",
                "tags": ["csi", "csi:provenance", f"project:{project_id}", "mirofish"],
                "project": f"mirofish-csi-{project_id}",
            }
            remote_ok, remote_response, remote_error = self._hivemind_request("POST", "/api/memories", payload)

        return {
            "ok": True,
            "provenance": record,
            "relation_results": relation_results,
            "remote_synced": remote_ok,
            "remote_error": remote_error,
            "remote_response": remote_response,
        }

    def get_project_snapshot(self, project_id: str) -> Dict[str, Any]:
        """读取项目 CSI 镜像快照。"""
        with self._lock:
            return self._load_project_cache(project_id)

    def _resolve_project_id(self, payload: Dict[str, Any]) -> str:
        project_id = str(payload.get("project_id") or "").strip()
        if not project_id:
            raise ValueError("project_id 不能为空")
        return project_id

    def ingest_sources(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        project_id = self._resolve_project_id(payload)
        sources = payload.get("sources")
        if sources is None and payload.get("source") is not None:
            sources = [payload.get("source")]
        if not isinstance(sources, list) or not sources:
            raise ValueError("sources/source 格式无效")

        created = []
        for item in sources:
            if not isinstance(item, dict):
                continue
            key = item.get("url") or item.get("source_id") or item.get("title") or uuid.uuid4().hex
            attributes = {
                "url": item.get("url"),
                "title": item.get("title"),
                "content": item.get("content") or item.get("text") or "",
                "source_type": item.get("source_type", "web"),
                "metadata": item.get("metadata", {}),
            }
            created.append(
                self.upsert_entity(
                    project_id=project_id,
                    entity_type="source",
                    key=str(key),
                    attributes=attributes,
                    metadata={"ingested_by": "faraday"},
                )["entity"]
            )
        return {"project_id": project_id, "sources": created, "count": len(created)}

    def extract_claims(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        project_id = self._resolve_project_id(payload)
        source_text = str(payload.get("source_text") or "").strip()
        source_id = payload.get("source_id") or payload.get("extract_id")
        claims = payload.get("claims")

        if not claims:
            if source_text:
                # naive deterministic claim extraction fallback
                units = [x.strip() for x in source_text.replace("\n", " ").split(".") if x.strip()]
                claims = [{"text": u} for u in units[:20]]
            else:
                claims = []

        if not isinstance(claims, list) or not claims:
            raise ValueError("未提供可提取的 claims")

        created = []
        for idx, c in enumerate(claims):
            ctext = c.get("text") if isinstance(c, dict) else str(c)
            if not ctext:
                continue
            entity = self.upsert_entity(
                project_id=project_id,
                entity_type="claim",
                key=f"{source_id or 'manual'}:{idx}:{ctext[:80]}",
                attributes={"text": ctext, "confidence": c.get("confidence", 0.5) if isinstance(c, dict) else 0.5},
                metadata={"extractor": "feynman"},
            )["entity"]
            if source_id:
                self.create_relation(
                    project_id=project_id,
                    relation_type="derived_from",
                    from_entity_id=entity["entity_id"],
                    to_entity_id=str(source_id),
                    metadata={"stage": "claim_extraction"},
                )
            created.append(entity)
        return {"project_id": project_id, "claims": created, "count": len(created)}

    def record_verdict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        project_id = self._resolve_project_id(payload)
        claim_id = str(payload.get("claim_id") or "").strip()
        verdict = str(payload.get("verdict") or "").strip().lower()
        if not claim_id or not verdict:
            raise ValueError("claim_id 与 verdict 必填")

        confidence = float(payload.get("confidence", 0.5))
        verdict_entity = self.upsert_entity(
            project_id=project_id,
            entity_type="verdict",
            key=f"{claim_id}:{verdict}",
            attributes={
                "verdict": verdict,
                "confidence": max(0.0, min(confidence, 1.0)),
                "reasoning": payload.get("reasoning", ""),
                "agent": payload.get("agent", "turing"),
            },
            metadata={"stage": "verdict"},
        )["entity"]

        relation_type = "supports"
        if verdict in {"disputed", "contradicted", "false", "reject"}:
            relation_type = "contradicts"

        rel = self.create_relation(
            project_id=project_id,
            relation_type=relation_type,
            from_entity_id=verdict_entity["entity_id"],
            to_entity_id=claim_id,
            metadata={"confidence": confidence},
        )["relation"]
        return {"project_id": project_id, "verdict": verdict_entity, "relation": rel}

    def log_trail(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        project_id = self._resolve_project_id(payload)
        trail = payload.get("trail")
        if not isinstance(trail, dict):
            raise ValueError("trail 必须是对象")

        trail_entity = self.upsert_entity(
            project_id=project_id,
            entity_type="trail",
            key=trail.get("id") or trail.get("name") or uuid.uuid4().hex,
            attributes=trail,
            metadata={"stage": "execution"},
        )["entity"]

        linked = []
        for related_id in trail.get("claim_ids", []) or []:
            linked.append(
                self.create_relation(
                    project_id=project_id,
                    relation_type="updates",
                    from_entity_id=trail_entity["entity_id"],
                    to_entity_id=str(related_id),
                    metadata={"kind": "trail_claim_link"},
                )["relation"]
            )
        return {"project_id": project_id, "trail": trail_entity, "linked_relations": linked}

    def promote_blueprint(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        project_id = self._resolve_project_id(payload)
        trail_ids = payload.get("trail_ids") or []
        if not trail_ids:
            raise ValueError("trail_ids 不能为空")

        blueprint = self.upsert_entity(
            project_id=project_id,
            entity_type="blueprint",
            key=payload.get("name") or f"bp-{uuid.uuid4().hex[:8]}",
            attributes={
                "trail_ids": [str(t) for t in trail_ids],
                "description": payload.get("description", ""),
                "success_rate": payload.get("success_rate", 0.0),
            },
            metadata={"stage": "promotion"},
        )["entity"]

        rels = []
        for tid in trail_ids:
            rels.append(
                self.create_relation(
                    project_id=project_id,
                    relation_type="derived_from",
                    from_entity_id=blueprint["entity_id"],
                    to_entity_id=str(tid),
                    metadata={"kind": "blueprint_trail"},
                )["relation"]
            )
        return {"project_id": project_id, "blueprint": blueprint, "relations": rels}

    def gate_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        project_id = self._resolve_project_id(payload)
        snapshot = self.get_project_snapshot(project_id)
        entities = snapshot.get("entities", {})
        relations = snapshot.get("relations", {})

        claim_count = sum(1 for e in entities.values() if e.get("entity_type") == "claim")
        verdict_count = sum(1 for e in entities.values() if e.get("entity_type") == "verdict")
        contradict_count = sum(1 for r in relations.values() if r.get("relation_type") == "contradicts")
        support_count = sum(1 for r in relations.values() if r.get("relation_type") == "supports")

        min_claims = int(payload.get("min_claims", 3))
        min_verdicts = int(payload.get("min_verdicts", 2))
        pass_gate = claim_count >= min_claims and verdict_count >= min_verdicts

        return {
            "project_id": project_id,
            "pass": pass_gate,
            "metrics": {
                "claims": claim_count,
                "verdicts": verdict_count,
                "supports": support_count,
                "contradictions": contradict_count,
            },
            "requirements": {"min_claims": min_claims, "min_verdicts": min_verdicts},
        }

    def generate_report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        project_id = self._resolve_project_id(payload)
        report_context = payload.get("report_context")
        if not isinstance(report_context, dict):
            raise ValueError("report_context 必须是对象")

        gate = self.gate_check({"project_id": project_id, **payload})
        if not gate["pass"]:
            return {"project_id": project_id, "generated": False, "gate": gate, "error": "gate_check 未通过"}

        if payload.get("resume_confirmed") is not True:
            return {
                "project_id": project_id,
                "generated": False,
                "gate": gate,
                "error": "需用户 resume_confirmed=true 后才可生成最终报告",
            }

        report_id = payload.get("report_id") or f"report_{uuid.uuid4().hex[:12]}"
        title = payload.get("report_title") or report_context.get("title") or "CSI Report"
        snapshot = self.get_project_snapshot(project_id)
        node_ids = list((snapshot.get("entities") or {}).keys())
        relation_ids = list((snapshot.get("relations") or {}).keys())

        provenance = self.persist_report_provenance(
            project_id=project_id,
            report_id=report_id,
            report_title=title,
            node_ids=node_ids,
            relation_ids=relation_ids,
            summary=payload.get("summary") or report_context.get("summary", ""),
            metadata={"gate_metrics": gate["metrics"]},
        )
        return {
            "project_id": project_id,
            "generated": True,
            "report_id": report_id,
            "report_title": title,
            "gate": gate,
            "provenance": provenance.get("provenance"),
        }

    def get_report_provenance(self, report_id: str) -> Optional[Dict[str, Any]]:
        # 先按当前项目集合扫描本地缓存
        for name in os.listdir(self._csi_dir):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self._csi_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                record = (cache.get("provenance") or {}).get(report_id)
                if record:
                    return record
            except Exception:  # noqa: BLE001
                continue
        return None
