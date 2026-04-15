"""
图谱构建服务
接口2：使用Zep API构建Standalone Graph
"""

import os
import uuid
import time
import threading
import json
import hashlib
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .text_processor import TextProcessor


@dataclass
class GraphInfo:
    """图谱信息"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    图谱构建服务
    负责调用Zep API构建知识图谱
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.provider = Config.GRAPH_PROVIDER
        self._zep_enabled = Config.zep_enabled()
        self.api_key = api_key or Config.ZEP_API_KEY
        self.client = None
        self.hivemind_api_url = Config.HIVEMIND_API_URL
        self.hivemind_api_key = Config.HIVEMIND_API_KEY

        if self.provider == 'zep' and self._zep_enabled:
            if not self.api_key:
                raise ValueError("ZEP_API_KEY 未配置")
            self.client = Zep(api_key=self.api_key)
        elif self.provider == 'hivemind':
            if not self.hivemind_api_url or not self.hivemind_api_key:
                raise ValueError("HIVEMIND_API_URL/HIVEMIND_API_KEY 未配置")
        elif self.provider == 'zep' and not self._zep_enabled:
            # Zep provider selected but disabled -- read-only local mode
            pass
        else:
            raise ValueError(f"不支持的 GRAPH_PROVIDER: {self.provider}")

        self.task_manager = TaskManager()

    @property
    def _local_graph_dir(self) -> str:
        path = os.path.join(Config.UPLOAD_FOLDER, 'graphs')
        os.makedirs(path, exist_ok=True)
        return path

    def _graph_file(self, graph_id: str) -> str:
        return os.path.join(self._local_graph_dir, f"{graph_id}.json")

    def _load_local_graph(self, graph_id: str) -> Dict[str, Any]:
        path = self._graph_file(graph_id)
        if not os.path.exists(path):
            raise FileNotFoundError(f"图谱不存在: {graph_id}")
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_local_graph(self, graph: Dict[str, Any]):
        path = self._graph_file(graph["graph_id"])
        graph["updated_at"] = datetime.now().isoformat()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)

    def _hm_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-Key": self.hivemind_api_key,
            "Authorization": f"Bearer {self.hivemind_api_key}",
        }

    def _hivemind_post(self, endpoint: str, payload: Dict[str, Any], timeout: float = 6.0) -> Dict[str, Any]:
        url = f"{self.hivemind_api_url}{endpoint}"
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(url=url, data=body, headers=self._hm_headers(), method="POST")
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HIVEMIND API 错误 {e.code}: {detail[:200]}")
        except URLError as e:
            raise RuntimeError(f"HIVEMIND API 不可达: {e.reason}")

    def _node_uuid(self, graph_id: str, node_type: str, name: str) -> str:
        raw = f"{graph_id}:{node_type}:{name.strip().lower()}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _edge_uuid(self, graph_id: str, source: str, target: str, relation: str) -> str:
        raw = f"{graph_id}:{source}:{target}:{relation}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        异步构建图谱
        
        Args:
            text: 输入文本
            ontology: 本体定义（来自接口1的输出）
            graph_name: 图谱名称
            chunk_size: 文本块大小
            chunk_overlap: 块重叠大小
            batch_size: 每批发送的块数量
            
        Returns:
            任务ID
        """
        # 创建任务
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )
        
        # 在后台线程中执行构建
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """图谱构建工作线程"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="开始构建图谱..."
            )
            
            # 1. 创建图谱
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"图谱已创建: {graph_id}"
            )
            
            # 2. 设置本体
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="本体已设置"
            )
            
            # 3. 文本分块
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"文本已分割为 {total_chunks} 个块"
            )
            
            # 4. 分批发送数据
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),  # 20-60%
                    message=msg
                )
            )
            
            # 5. 等待Zep处理完成
            self.task_manager.update_task(
                task_id,
                progress=60,
                message="等待Zep处理数据..."
            )
            
            self._wait_for_episodes(
                episode_uuids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),  # 60-90%
                    message=msg
                )
            )
            
            # 6. 获取图谱信息
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="获取图谱信息..."
            )
            
            graph_info = self._get_graph_info(graph_id)
            
            # 完成
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """创建Zep图谱（公开方法）"""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        if self.provider == 'zep':
            self.client.graph.create(
                graph_id=graph_id,
                name=name,
                description="MiroFish Social Simulation Graph"
            )
        else:
            graph = {
                "graph_id": graph_id,
                "name": name,
                "provider": "hivemind",
                "ontology": {"entity_types": [], "edge_types": []},
                "nodes": [],
                "edges": [],
                "episodes": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            self._save_local_graph(graph)
        return graph_id
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """设置图谱本体（公开方法）"""
        if self.provider == 'hivemind':
            graph = self._load_local_graph(graph_id)
            graph["ontology"] = {
                "entity_types": ontology.get("entity_types", []),
                "edge_types": ontology.get("edge_types", []),
            }
            nodes = graph.get("nodes", [])
            seen = {n["uuid"] for n in nodes}
            for entity in ontology.get("entity_types", []):
                label = entity.get("name", "Entity")
                description = entity.get("description", "")
                examples = entity.get("examples", [])[:3] or [label]
                for ex in examples:
                    node_uuid = self._node_uuid(graph_id, label, ex)
                    if node_uuid in seen:
                        continue
                    seen.add(node_uuid)
                    nodes.append({
                        "uuid": node_uuid,
                        "name": ex,
                        "labels": ["Entity", label],
                        "summary": description,
                        "attributes": {
                            "entity_type": label,
                            "source": "ontology_seed"
                        },
                        "created_at": datetime.now().isoformat(),
                    })
            graph["nodes"] = nodes
            self._save_local_graph(graph)
            return

        import warnings
        from typing import Optional
        from pydantic import Field
        from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel
        
        # 抑制 Pydantic v2 关于 Field(default=None) 的警告
        # 这是 Zep SDK 要求的用法，警告来自动态类创建，可以安全忽略
        warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')
        
        # Zep 保留名称，不能作为属性名
        RESERVED_NAMES = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}
        
        def safe_attr_name(attr_name: str) -> str:
            """将保留名称转换为安全名称"""
            if attr_name.lower() in RESERVED_NAMES:
                return f"entity_{attr_name}"
            return attr_name
        
        # 动态创建实体类型
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")
            
            # 创建属性字典和类型注解（Pydantic v2 需要）
            attrs = {"__doc__": description}
            annotations = {}
            
            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # 使用安全名称
                attr_desc = attr_def.get("description", attr_name)
                # Zep API 需要 Field 的 description，这是必需的
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[EntityText]  # 类型注解
            
            attrs["__annotations__"] = annotations
            
            # 动态创建类
            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class
        
        # 动态创建边类型
        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")
            
            # 创建属性字典和类型注解
            attrs = {"__doc__": description}
            annotations = {}
            
            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # 使用安全名称
                attr_desc = attr_def.get("description", attr_name)
                # Zep API 需要 Field 的 description，这是必需的
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]  # 边属性用str类型
            
            attrs["__annotations__"] = annotations
            
            # 动态创建类
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description
            
            # 构建source_targets
            source_targets = []
            for st in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(
                        source=st.get("source", "Entity"),
                        target=st.get("target", "Entity")
                    )
                )
            
            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)
        
        # 调用Zep API设置本体
        if entity_types or edge_definitions:
            self.client.graph.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """分批添加文本到图谱，返回所有 episode 的 uuid 列表"""
        if self.provider == 'hivemind':
            graph = self._load_local_graph(graph_id)
            episodes = graph.get("episodes", [])
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            node_ids = {n["uuid"] for n in nodes}
            edge_ids = {e["uuid"] for e in edges}
            total_chunks = len(chunks)
            existing_entities = [n for n in nodes if "Entity" in (n.get("labels") or [])]

            for idx, chunk in enumerate(chunks):
                ep_uuid = f"ep_{uuid.uuid4().hex[:12]}"
                chunk_name = f"Chunk {len(episodes) + 1}"
                chunk_uuid = self._node_uuid(graph_id, "DocumentChunk", chunk_name)
                if chunk_uuid not in node_ids:
                    node_ids.add(chunk_uuid)
                    nodes.append({
                        "uuid": chunk_uuid,
                        "name": chunk_name,
                        "labels": ["Node", "DocumentChunk"],
                        "summary": chunk[:300],
                        "attributes": {"content": chunk[:2000]},
                        "created_at": datetime.now().isoformat(),
                    })

                # 简单实体链接：基于名称出现在文本中的实体进行连接
                matched_entities = []
                chunk_lower = chunk.lower()
                for entity in existing_entities:
                    name = (entity.get("name") or "").strip()
                    if name and name.lower() in chunk_lower:
                        matched_entities.append(entity)

                for entity in matched_entities:
                    rel = "mentions"
                    e_uuid = self._edge_uuid(graph_id, chunk_uuid, entity["uuid"], rel)
                    if e_uuid not in edge_ids:
                        edge_ids.add(e_uuid)
                        edges.append({
                            "uuid": e_uuid,
                            "name": rel.upper(),
                            "fact": f"{chunk_name} mentions {entity['name']}",
                            "fact_type": rel,
                            "source_node_uuid": chunk_uuid,
                            "target_node_uuid": entity["uuid"],
                            "attributes": {},
                            "created_at": datetime.now().isoformat(),
                            "episodes": [ep_uuid],
                        })

                # 实体共现边
                for i in range(len(matched_entities)):
                    for j in range(i + 1, len(matched_entities)):
                        s = matched_entities[i]["uuid"]
                        t = matched_entities[j]["uuid"]
                        rel = "co_occurs"
                        e_uuid = self._edge_uuid(graph_id, s, t, rel)
                        if e_uuid not in edge_ids:
                            edge_ids.add(e_uuid)
                            edges.append({
                                "uuid": e_uuid,
                                "name": "CO_OCCURS",
                                "fact": f"{matched_entities[i]['name']} co-occurs with {matched_entities[j]['name']}",
                                "fact_type": rel,
                                "source_node_uuid": s,
                                "target_node_uuid": t,
                                "attributes": {},
                                "created_at": datetime.now().isoformat(),
                                "episodes": [ep_uuid],
                            })

                episodes.append({
                    "uuid": ep_uuid,
                    "type": "text",
                    "data": chunk,
                    "processed": True,
                    "created_at": datetime.now().isoformat(),
                })

                # 可选: 同步到 HIVEMIND memories（默认关闭，避免拖慢构建）
                if Config.HIVEMIND_SYNC_EPISODES:
                    try:
                        self._hivemind_post(
                            "/api/memories",
                            {
                                "title": f"MiroFish Episode {ep_uuid}",
                                "content": chunk,
                                "project": f"mirofish/{graph_id}",
                                "tags": ["mirofish", "episode", graph_id],
                            },
                            timeout=3.0,
                        )
                    except Exception:
                        # 不阻塞图构建流程
                        pass

                if progress_callback:
                    progress_callback(
                        f"发送第 {idx + 1}/{total_chunks} 批数据...",
                        (idx + 1) / max(total_chunks, 1),
                    )

            graph["episodes"] = episodes
            graph["nodes"] = nodes
            graph["edges"] = edges
            self._save_local_graph(graph)
            return [ep["uuid"] for ep in episodes]

        episode_uuids = []
        total_chunks = len(chunks)
        
        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            
            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"发送第 {batch_num}/{total_batches} 批数据 ({len(batch_chunks)} 块)...",
                    progress
                )
            
            # 构建episode数据
            episodes = [
                EpisodeData(data=chunk, type="text")
                for chunk in batch_chunks
            ]
            
            # 发送到Zep
            try:
                batch_result = self.client.graph.add_batch(
                    graph_id=graph_id,
                    episodes=episodes
                )
                
                # 收集返回的 episode uuid
                if batch_result and isinstance(batch_result, list):
                    for ep in batch_result:
                        ep_uuid = getattr(ep, 'uuid_', None) or getattr(ep, 'uuid', None)
                        if ep_uuid:
                            episode_uuids.append(ep_uuid)
                
                # 避免请求过快
                time.sleep(1)
                
            except Exception as e:
                if progress_callback:
                    progress_callback(f"批次 {batch_num} 发送失败: {str(e)}", 0)
                raise
        
        return episode_uuids
    
    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        """等待所有 episode 处理完成（通过查询每个 episode 的 processed 状态）"""
        if self.provider == 'hivemind':
            if progress_callback:
                progress_callback("HIVEMIND 模式无需等待异步处理", 1.0)
            return

        if not episode_uuids:
            if progress_callback:
                progress_callback("无需等待（没有 episode）", 1.0)
            return
        
        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)
        
        if progress_callback:
            progress_callback(f"开始等待 {total_episodes} 个文本块处理...", 0)
        
        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        f"部分文本块超时，已完成 {completed_count}/{total_episodes}",
                        completed_count / total_episodes
                    )
                break
            
            # 检查每个 episode 的处理状态
            for ep_uuid in list(pending_episodes):
                try:
                    episode = self.client.graph.episode.get(uuid_=ep_uuid)
                    is_processed = getattr(episode, 'processed', False)
                    
                    if is_processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1
                        
                except Exception as e:
                    # 忽略单个查询错误，继续
                    pass
            
            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    f"Zep处理中... {completed_count}/{total_episodes} 完成, {len(pending_episodes)} 待处理 ({elapsed}秒)",
                    completed_count / total_episodes if total_episodes > 0 else 0
                )
            
            if pending_episodes:
                time.sleep(3)  # 每3秒检查一次
        
        if progress_callback:
            progress_callback(f"处理完成: {completed_count}/{total_episodes}", 1.0)
    
    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """获取图谱信息"""
        if self.provider == 'hivemind':
            graph = self._load_local_graph(graph_id)
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            entity_types = set()
            for node in nodes:
                for label in node.get("labels", []):
                    if label not in ["Entity", "Node", "DocumentChunk"]:
                        entity_types.add(label)
            return GraphInfo(
                graph_id=graph_id,
                node_count=len(nodes),
                edge_count=len(edges),
                entity_types=list(entity_types),
            )

        # 获取节点（分页）
        nodes = fetch_all_nodes(self.client, graph_id)

        # 获取边（分页）
        edges = fetch_all_edges(self.client, graph_id)

        # 统计实体类型
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        获取完整图谱数据（包含详细信息）
        
        Args:
            graph_id: 图谱ID
            
        Returns:
            包含nodes和edges的字典，包括时间信息、属性等详细数据
        """
        if self.provider == 'hivemind':
            graph = self._load_local_graph(graph_id)
            nodes_data = graph.get("nodes", [])
            edges_data = graph.get("edges", [])

            # 补齐展示字段，保持与前端结构兼容
            node_map = {n["uuid"]: n.get("name", "") for n in nodes_data}
            normalized_edges = []
            for edge in edges_data:
                normalized_edges.append({
                    "uuid": edge.get("uuid"),
                    "name": edge.get("name", ""),
                    "fact": edge.get("fact", ""),
                    "fact_type": edge.get("fact_type") or edge.get("name", ""),
                    "source_node_uuid": edge.get("source_node_uuid"),
                    "target_node_uuid": edge.get("target_node_uuid"),
                    "source_node_name": node_map.get(edge.get("source_node_uuid"), ""),
                    "target_node_name": node_map.get(edge.get("target_node_uuid"), ""),
                    "attributes": edge.get("attributes", {}),
                    "created_at": edge.get("created_at"),
                    "valid_at": edge.get("valid_at"),
                    "invalid_at": edge.get("invalid_at"),
                    "expired_at": edge.get("expired_at"),
                    "episodes": edge.get("episodes", []),
                })

            return {
                "graph_id": graph_id,
                "nodes": nodes_data,
                "edges": normalized_edges,
                "node_count": len(nodes_data),
                "edge_count": len(normalized_edges),
            }

        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # 创建节点映射用于获取节点名称
        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""
        
        nodes_data = []
        for node in nodes:
            # 获取创建时间
            created_at = getattr(node, 'created_at', None)
            if created_at:
                created_at = str(created_at)
            
            nodes_data.append({
                "uuid": node.uuid_,
                "name": node.name,
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
                "created_at": created_at,
            })
        
        edges_data = []
        for edge in edges:
            # 获取时间信息
            created_at = getattr(edge, 'created_at', None)
            valid_at = getattr(edge, 'valid_at', None)
            invalid_at = getattr(edge, 'invalid_at', None)
            expired_at = getattr(edge, 'expired_at', None)
            
            # 获取 episodes
            episodes = getattr(edge, 'episodes', None) or getattr(edge, 'episode_ids', None)
            if episodes and not isinstance(episodes, list):
                episodes = [str(episodes)]
            elif episodes:
                episodes = [str(e) for e in episodes]
            
            # 获取 fact_type
            fact_type = getattr(edge, 'fact_type', None) or edge.name or ""
            
            edges_data.append({
                "uuid": edge.uuid_,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": fact_type,
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge.attributes or {},
                "created_at": str(created_at) if created_at else None,
                "valid_at": str(valid_at) if valid_at else None,
                "invalid_at": str(invalid_at) if invalid_at else None,
                "expired_at": str(expired_at) if expired_at else None,
                "episodes": episodes or [],
            })
        
        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }
    
    def delete_graph(self, graph_id: str):
        """删除图谱"""
        if self.provider == 'hivemind':
            path = self._graph_file(graph_id)
            if os.path.exists(path):
                os.remove(path)
            return
        self.client.graph.delete(graph_id=graph_id)
