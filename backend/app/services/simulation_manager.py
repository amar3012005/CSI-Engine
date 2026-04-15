"""
OASIS模拟管理器
管理Twitter和Reddit双平台并行模拟
使用预设脚本 + LLM智能生成配置参数
"""

import os
import json
import shutil
import re
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import ZepEntityReader, FilteredEntities, EntityNode
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters
from .simulation_csi_local import SimulationCSILocalStore
from ..models.project import ProjectManager

logger = get_logger('mirofish.simulation')


class SimulationStatus(str, Enum):
    """模拟状态"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # 模拟被手动停止
    COMPLETED = "completed"  # 模拟自然完成
    FAILED = "failed"


class PlatformType(str, Enum):
    """平台类型"""
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """模拟状态"""
    simulation_id: str
    project_id: str
    graph_id: str
    
    # 平台启用状态
    enable_twitter: bool = True
    enable_reddit: bool = True
    
    # 状态
    status: SimulationStatus = SimulationStatus.CREATED
    
    # 准备阶段数据
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)
    config_mode: str = "social"
    config_mode_label: str = "Dual-Platform Social Simulation"
    
    # 配置生成信息
    profiles_generated: bool = False
    config_generated: bool = False
    config_reasoning: str = ""
    csi_initialized: bool = False
    csi_rounds: int = 0
    csi_artifacts_ready: bool = False
    
    # 运行时数据
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"
    simulation_requirement: str = ""
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    
    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 错误信息
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """完整状态字典（内部使用）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_mode": self.config_mode,
            "config_mode_label": self.config_mode_label,
            "profiles_generated": self.profiles_generated,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "csi_initialized": self.csi_initialized,
            "csi_rounds": self.csi_rounds,
            "csi_artifacts_ready": self.csi_artifacts_ready,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "simulation_requirement": self.simulation_requirement,
            "checkpoints": self.checkpoints,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """简化状态字典（API返回使用）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_mode": self.config_mode,
            "config_mode_label": self.config_mode_label,
            "profiles_generated": self.profiles_generated,
            "config_generated": self.config_generated,
            "csi_initialized": self.csi_initialized,
            "csi_rounds": self.csi_rounds,
            "csi_artifacts_ready": self.csi_artifacts_ready,
            "simulation_requirement": self.simulation_requirement,
            "checkpoints": self.checkpoints,
            "error": self.error,
        }


class SimulationManager:
    """
    模拟管理器
    
    核心功能：
    1. 从Zep图谱读取实体并过滤
    2. 生成OASIS Agent Profile
    3. 使用LLM智能生成模拟配置参数
    4. 准备预设脚本所需的所有文件
    """
    
    # 模拟数据存储目录
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
    def __init__(self):
        # 确保目录存在
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)
        
        # 内存中的模拟状态缓存
        self._simulations: Dict[str, SimulationState] = {}

    def _tokenize_query(self, text: str) -> set:
        if not text:
            return set()
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_\\-]{2,}", text.lower())
        return set(tokens)

    ENTITY_TYPE_PRIORITY_WEIGHTS = {
        "physicist": 3.4,
        "physicsprofessor": 3.2,
        "researcher": 3.0,
        "scienceeducator": 2.8,
        "physicsstudent": 2.3,
        "journalist": 2.1,
        "physicsjournal": 2.0,
        "sciencemagazine": 1.9,
        "organization": 1.2,
        "person": 0.8,
        "node": -2.0,
    }

    def _entity_professional_score(self, entity, query_tokens: set) -> float:
        """Heuristic score for selecting professional entities and suppressing noisy chunk nodes."""
        et = (entity.get_entity_type() or "").lower()
        name = (entity.name or "").lower()
        summary = (entity.summary or "").lower()
        attrs_text = " ".join([str(v) for v in (entity.attributes or {}).values()]).lower()
        bag = f"{name} {summary} {attrs_text}"

        score = 0.0

        # Penalize chunk/noise-like entities.
        if name.startswith("chunk_") or et in {"documentchunk", "chunk"}:
            score -= 2.5
        # Penalize placeholder/common synthetic names frequently produced by extraction.
        placeholder_names = {
            "john smith", "john walker", "jane doe", "alice johnson",
            "a random citizen", "a generic ngo", "anonymous"
        }
        if name in placeholder_names:
            score -= 2.2
        if "unknown profession" in bag:
            score -= 1.2
        if et in {"person", "student", "alumni", "professor", "expert", "faculty", "journalist", "official"}:
            score += 2.2
        if et in {"company", "organization", "university", "governmentagency", "institution", "ngo", "mediaoutlet"}:
            score += 1.8
        score += self.ENTITY_TYPE_PRIORITY_WEIGHTS.get(et, 0.0)

        # Professional signal keywords.
        pro_keywords = (
            "founder", "cto", "ceo", "professor", "dr.", "doctor", "research",
            "ai", "engineer", "scientist", "university", "institute", "gmbh",
            "technology", "analysis", "policy", "finance", "architecture"
        )
        score += sum(0.15 for kw in pro_keywords if kw in bag)

        # Query relevance
        if query_tokens:
            overlap = sum(1 for t in query_tokens if t in bag)
            score += min(overlap * 0.35, 2.8)
            # If query has clear topic but entity has no overlap, gently demote.
            if overlap == 0 and len(query_tokens) >= 3:
                score -= 0.9

        # Prefer richer summaries
        score += min(len(summary) / 1200.0, 1.0)
        return score

    def _priority_rank(self, entity) -> float:
        et = (entity.get_entity_type() or "").lower()
        return self.ENTITY_TYPE_PRIORITY_WEIGHTS.get(et, 0.0)

    def _select_professional_entities(
        self,
        entities: List,
        max_agents: int,
        simulation_requirement: str,
        user_query: Optional[str] = None,
    ) -> List:
        """
        Select top entities for higher-quality professional agent pool.
        Keeps lifecycle unchanged but improves who gets profiled.
        """
        if not entities:
            return []
        capped = max(1, min(int(max_agents or 25), 200))
        query_tokens = self._tokenize_query((user_query or "") + " " + (simulation_requirement or ""))
        scored = [((self._entity_professional_score(e, query_tokens) + self._priority_rank(e)), e) for e in entities]
        scored.sort(key=lambda x: x[0], reverse=True)
        # Prefer meaningful entities: require minimal score; fallback to top-k if too few.
        threshold = 0.6 if query_tokens else 0.0
        selected = [e for s, e in scored if s >= threshold and (e.get_entity_type() or "").lower() not in {"node"}][:capped]
        if len(selected) < min(8, capped):
            selected = [e for _, e in scored if (e.get_entity_type() or "").lower() not in {"node"}][:capped]

        # Ensure representation of top-priority ontology types when available.
        target_types = [
            "physicist", "physicsprofessor", "researcher", "scienceeducator",
            "physicsstudent", "journalist", "physicsjournal", "sciencemagazine"
        ]
        selected_by_name = {e.name.lower() for e in selected}
        for t in target_types:
            if len(selected) >= capped:
                break
            for _, e in scored:
                et = (e.get_entity_type() or "").lower()
                if et == t and e.name.lower() not in selected_by_name:
                    selected.append(e)
                    selected_by_name.add(e.name.lower())
                    break

        # final cap after representation pass
        selected = selected[:capped]
        logger.info(f"专业实体筛选完成: 原始={len(entities)}, 选中={len(selected)}, max_agents={capped}")
        return selected

    FAMOUS_TOPIC_EXPERTS = {
        "quantum": [
            ("Richard Feynman", "expert", "Theoretical physicist known for quantum electrodynamics and Feynman diagrams."),
            ("Niels Bohr", "expert", "Pioneer of quantum theory and complementarity."),
            ("Werner Heisenberg", "expert", "Known for uncertainty principle and matrix mechanics."),
            ("Erwin Schrodinger", "expert", "Wave mechanics and foundational quantum interpretations."),
            ("Paul Dirac", "expert", "Relativistic quantum mechanics and antimatter prediction."),
        ],
        "antimatter": [
            ("Paul Dirac", "expert", "Predicted antimatter through the Dirac equation."),
            ("Carl Anderson", "expert", "Discovered the positron experimentally."),
            ("Carlo Rubbia", "expert", "Led proton-antiproton collider experiments."),
            ("Gerald Gabrielse", "expert", "High-precision antimatter property measurements."),
        ],
        "rocket": [
            ("Wernher von Braun", "expert", "Rocket engineering and Saturn program history."),
            ("Katherine Johnson", "expert", "Orbital mechanics and trajectory analysis."),
            ("Elon Musk", "publicfigure", "Commercial launch systems and reusable rockets."),
            ("Gwynne Shotwell", "expert", "Launch operations and aerospace execution leadership."),
        ],
        "artemis": [
            ("Bill Nelson", "official", "NASA leadership and Artemis policy direction."),
            ("Jim Free", "official", "NASA exploration systems oversight."),
            ("John Honeycutt", "expert", "SLS program management expertise."),
            ("Cathy Koerner", "expert", "Orion and mission operations leadership."),
        ],
    }

    def _infer_topic_keys(self, simulation_requirement: str, user_query: Optional[str]) -> List[str]:
        text = f"{simulation_requirement or ''} {user_query or ''}".lower()
        found = []
        for key in self.FAMOUS_TOPIC_EXPERTS.keys():
            if key in text:
                found.append(key)
        return found

    def _inject_famous_personas(
        self,
        entities: List[EntityNode],
        simulation_requirement: str,
        user_query: Optional[str],
        ratio: float = 0.2,
        max_agents: int = 25,
    ) -> List[EntityNode]:
        """
        Inject topic-relevant famous experts into candidate pool.
        """
        ratio = max(0.0, min(float(ratio), 0.6))
        if ratio <= 0:
            return entities

        keys = self._infer_topic_keys(simulation_requirement, user_query)
        if not keys:
            return entities

        candidates = []
        seen_names = {e.name.lower() for e in entities}
        for k in keys:
            for name, etype, summary in self.FAMOUS_TOPIC_EXPERTS.get(k, []):
                if name.lower() in seen_names:
                    continue
                uid = hashlib.md5(f"famous:{k}:{name}".encode("utf-8")).hexdigest()
                candidates.append(
                    EntityNode(
                        uuid=f"famous_{uid[:16]}",
                        name=name,
                        labels=["Entity", etype],
                        summary=summary,
                        attributes={"source": "topic_famous_pool", "topic": k, "is_famous_persona": True},
                        related_edges=[],
                        related_nodes=[],
                    )
                )
                seen_names.add(name.lower())

        if not candidates:
            return entities

        quota = max(1, int(max_agents * ratio))
        injected = candidates[:quota]
        # Replace tail low-score entities to keep bounded pool quality.
        combined = entities[: max(0, max_agents - len(injected))] + injected
        logger.info(f"注入主题知名专家: topics={keys}, injected={len(injected)}, ratio={ratio}")
        return combined

    def _is_famous_persona(self, entity: EntityNode) -> bool:
        attrs = entity.attributes or {}
        return bool(attrs.get("is_famous_persona"))

    def _apply_source_first_mix(
        self,
        entities: List[EntityNode],
        max_agents: int,
        source_first_ratio: float = 0.8,
    ) -> List[EntityNode]:
        """
        Enforce majority of source-grounded entities in final candidate pool.
        """
        if not entities:
            return []
        cap = max(1, min(int(max_agents), 200))
        ratio = max(0.5, min(float(source_first_ratio), 0.95))
        src_quota = max(1, int(cap * ratio))
        fam_quota = max(0, cap - src_quota)

        source_entities = [e for e in entities if not self._is_famous_persona(e)]
        famous_entities = [e for e in entities if self._is_famous_persona(e)]

        selected = source_entities[:src_quota] + famous_entities[:fam_quota]
        # Backfill if one side is short.
        if len(selected) < cap:
            used = {id(x) for x in selected}
            for e in entities:
                if id(e) not in used:
                    selected.append(e)
                    if len(selected) >= cap:
                        break
        return selected[:cap]
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """获取模拟数据目录"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """保存模拟状态到文件"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        state.updated_at = datetime.now().isoformat()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        
        self._simulations[state.simulation_id] = state
    
    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """从文件加载模拟状态"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]
        
        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_mode=data.get("config_mode", "social"),
            config_mode_label=data.get("config_mode_label", "Dual-Platform Social Simulation"),
            profiles_generated=data.get("profiles_generated", False),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            csi_initialized=data.get("csi_initialized", False),
            csi_rounds=data.get("csi_rounds", 0),
            csi_artifacts_ready=data.get("csi_artifacts_ready", False),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            simulation_requirement=data.get("simulation_requirement", ""),
            checkpoints=data.get("checkpoints", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        
        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        config_mode: str = "social",
    ) -> SimulationState:
        """
        创建新的模拟
        
        Args:
            project_id: 项目ID
            graph_id: Zep图谱ID
            enable_twitter: 是否启用Twitter模拟
            enable_reddit: 是否启用Reddit模拟
            
        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
            config_mode=config_mode,
            config_mode_label={
                "deepresearch": "DeepResearch / CSI Workflow",
                "web_research": "Web Research (query-only)",
                "social": "Dual-Platform Social Simulation",
            }.get(config_mode, "Dual-Platform Social Simulation"),
        )
        
        self._save_simulation_state(state)
        logger.info(f"创建模拟: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3,
        config_mode: str = "social",
        max_agents: int = 25,
        professional_mode: bool = True,
        user_query: Optional[str] = None,
        min_qualification_score: float = 0.75,
        naming_mode: str = "hybrid",
        allow_famous_personas: bool = True,
        famous_persona_ratio: float = 0.2,
        source_first_mode: bool = True,
        source_first_ratio: float = 0.8
    ) -> SimulationState:
        """
        准备模拟环境（全程自动化）
        
        步骤：
        1. 从Zep图谱读取并过滤实体
        2. 为每个实体生成OASIS Agent Profile（可选LLM增强，支持并行）
        3. 使用LLM智能生成模拟配置参数（时间、活跃度、发言频率等）
        4. 保存配置文件和Profile文件
        5. 复制预设脚本到模拟目录
        
        Args:
            simulation_id: 模拟ID
            simulation_requirement: 模拟需求描述（用于LLM生成配置）
            document_text: 原始文档内容（用于LLM理解背景）
            defined_entity_types: 预定义的实体类型（可选）
            use_llm_for_profiles: 是否使用LLM生成详细人设
            progress_callback: 进度回调函数 (stage, progress, message)
            parallel_profile_count: 并行生成人设的数量，默认3
            
        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"模拟不存在: {simulation_id}")
        
        try:
            state.status = SimulationStatus.PREPARING
            state.simulation_requirement = simulation_requirement or state.simulation_requirement
            mode_labels = {
                "deepresearch": "DeepResearch / CSI Workflow",
                "web_research": "Web Research (query-only)",
                "social": "Dual-Platform Social Simulation",
            }
            state.config_mode = config_mode
            state.config_mode_label = mode_labels.get(config_mode, "Dual-Platform Social Simulation")
            self._save_simulation_state(state)

            sim_dir = self._get_simulation_dir(simulation_id)

            # ====================================================================
            # WEB RESEARCH MODE — generate team from query, skip graph entirely
            # ====================================================================
            if config_mode == "web_research":
                return self._prepare_web_research(
                    state=state,
                    sim_dir=sim_dir,
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    max_agents=max_agents,
                    progress_callback=progress_callback,
                )

            # ========== 阶段1: 读取并过滤实体 ==========
            if progress_callback:
                progress_callback("reading", 0, "正在连接Zep图谱...")
            
            reader = ZepEntityReader()
            
            if progress_callback:
                progress_callback("reading", 30, "正在读取节点数据...")
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )

            if professional_mode:
                filtered.entities = self._select_professional_entities(
                    entities=filtered.entities,
                    max_agents=max_agents,
                    simulation_requirement=simulation_requirement,
                    user_query=user_query
                )
                if allow_famous_personas and naming_mode in {"hybrid", "topic_famous_pool"}:
                    filtered.entities = self._inject_famous_personas(
                        entities=filtered.entities,
                        simulation_requirement=simulation_requirement,
                        user_query=user_query,
                        ratio=famous_persona_ratio,
                        max_agents=max_agents
                    )
                if naming_mode == "topic_famous_pool":
                    # keep only injected famous + top professional fallback if needed
                    filtered.entities = filtered.entities[:max_agents]
                if source_first_mode and naming_mode in {"hybrid", "real_entities_only"}:
                    filtered.entities = self._apply_source_first_mix(
                        entities=filtered.entities,
                        max_agents=max_agents,
                        source_first_ratio=source_first_ratio
                    )
                filtered.filtered_count = len(filtered.entities)
                filtered.entity_types = {e.get_entity_type() for e in filtered.entities if e.get_entity_type()}
            
            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)
            
            if progress_callback:
                progress_callback(
                    "reading", 100, 
                    f"完成，共 {filtered.filtered_count} 个实体",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "没有找到符合条件的实体，请检查图谱是否正确构建"
                self._save_simulation_state(state)
                return state
            
            total_entities = len(filtered.entities)

            # ========== 阶段2: 先生成统一的Agent执行配置 ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0, 
                    "正在分析实体并生成Agent执行配置...",
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator(usage_scope=simulation_id)
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30, 
                    "正在调用LLM生成统一Agent配置...",
                    current=1,
                    total=3
                )
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                config_mode=config_mode,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70, 
                    "正在保存Agent执行配置...",
                    current=2,
                    total=3
                )
            
            # 保存配置文件
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())

            state.config_reasoning = sim_params.generation_reasoning
            state.config_mode = sim_params.config_mode
            state.config_mode_label = sim_params.mode_label
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100, 
                    "统一Agent执行配置已生成",
                    current=3,
                    total=3
                )

            # ========== 阶段3: 基于统一Agent配置生成人设与平台输出 ==========
            if progress_callback:
                progress_callback(
                    "generating_profiles", 0,
                    "开始基于统一Agent配置生成画像...",
                    current=0,
                    total=total_entities
                )

            agent_seed_map = {
                cfg.entity_uuid: {
                    "role": cfg.role,
                    "skills": cfg.skills,
                    "qualification_score": cfg.qualification_score,
                    "profession": cfg.role,
                    "interested_topics": cfg.research_focus,
                    "source_origin": cfg.source_origin,
                    "source_priority": cfg.source_priority,
                    "entity_summary": cfg.entity_summary,
                }
                for cfg in sim_params.agent_configs
            }

            entity_by_uuid = {entity.uuid: entity for entity in filtered.entities}
            ordered_entities = [
                entity_by_uuid[cfg.entity_uuid]
                for cfg in sim_params.agent_configs
                if cfg.entity_uuid in entity_by_uuid
            ]
            if ordered_entities:
                filtered.entities = ordered_entities
                total_entities = len(filtered.entities)

            generator = OasisProfileGenerator(graph_id=state.graph_id, usage_scope=simulation_id)

            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles",
                        int(current / total * 100),
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )

            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"

            profiles = generator.generate_profiles_from_entities(
                entities=filtered.entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,
                parallel_count=parallel_profile_count,
                realtime_output_path=realtime_output_path,
                output_platform=realtime_platform,
                agent_seeds=agent_seed_map
            )

            if professional_mode:
                q_floor = max(0.0, min(float(min_qualification_score), 1.0))
                for p in profiles:
                    if p and (p.qualification_score or 0.0) < q_floor:
                        p.qualification_score = q_floor

            state.profiles_count = len(profiles)
            state.profiles_generated = True

            if progress_callback:
                progress_callback(
                    "generating_profiles", 95,
                    "正在写入平台画像文件...",
                    current=total_entities,
                    total=total_entities
                )

            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )

            if state.enable_twitter:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )

            if progress_callback:
                progress_callback(
                    "generating_profiles", 100,
                    f"完成，共 {len(profiles)} 个Profile",
                    current=len(profiles),
                    total=len(profiles)
                )

            # ========== 阶段4: 初始化本地CSI工作状态 ==========
            if progress_callback:
                progress_callback(
                    "building_csi",
                    0,
                    "正在初始化本地CSI工作状态...",
                    current=0,
                    total=2
                )

            if config_mode == "deepresearch":
                csi_store = SimulationCSILocalStore()
                profiles_payload = [
                    p.to_dict() if hasattr(p, "to_dict") else (p if isinstance(p, dict) else getattr(p, "__dict__", {}))
                    for p in profiles
                ]
                simulation_config_dict = sim_params.to_dict()
                csi_store._write_json(
                    os.path.join(sim_dir, "csi", "simulation_config_snapshot.json"),
                    simulation_config_dict,
                )
                csi_store._write_json(
                    os.path.join(sim_dir, "csi", "profiles_snapshot.json"),
                    profiles_payload,
                )
                csi_result = csi_store.initialize_from_prepare(
                    simulation_id=simulation_id,
                    project_id=state.project_id,
                    graph_id=state.graph_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    simulation_config=simulation_config_dict,
                    profiles=profiles_payload,
                    bootstrap_rounds=0,  # skip template bootstrap — CSI research engine handles all rounds
                )
                state.csi_initialized = True
                state.csi_rounds = csi_result.get("state", {}).get("round_count", 0)
                state.csi_artifacts_ready = True
                if progress_callback:
                    progress_callback(
                        "building_csi",
                        100,
                        f"本地CSI工作状态已初始化: claims={csi_result.get('state', {}).get('claim_count', 0)}, trials={csi_result.get('state', {}).get('trial_count', 0)}",
                        current=1,
                        total=1
                    )
            else:
                state.csi_initialized = False
                state.csi_rounds = 0
                state.csi_artifacts_ready = False
                if progress_callback:
                    progress_callback(
                        "building_csi",
                        100,
                        "当前模式未启用本地CSI工作状态",
                        current=1,
                        total=1
                    )

            state.config_generated = True
            
            # 注意：运行脚本保留在 backend/scripts/ 目录，不再复制到模拟目录
            # 启动模拟时，simulation_runner 会从 scripts/ 目录运行脚本
            
            # 更新状态
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"模拟准备完成: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.error(f"模拟准备失败: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
    # ------------------------------------------------------------------
    # Web-research prepare helper
    # ------------------------------------------------------------------

    def _prepare_web_research(
        self,
        state: SimulationState,
        sim_dir: str,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        max_agents: int = 25,
        progress_callback: Optional[callable] = None,
    ) -> SimulationState:
        """Prepare simulation for web-only research mode.

        Generates a research team from the query via ``ResearchTeamGenerator``,
        builds a minimal ``SimulationParameters`` config, and initializes the
        CSI store — all without touching the knowledge graph.
        """
        try:
            from .research_team_generator import ResearchTeamGenerator
        except ImportError:
            logger.error(
                "research_team_generator module not available; "
                "cannot prepare web_research mode for %s",
                simulation_id,
            )
            state.status = SimulationStatus.FAILED
            state.error = "ResearchTeamGenerator module is not yet available"
            self._save_simulation_state(state)
            return state

        from ..utils.llm_client import LLMClient
        from .simulation_config_generator import (
            SimulationParameters,
            TimeSimulationConfig,
            EventConfig,
            ResearchWorkflowConfig,
            ResearchAgentAssignment,
            AgentActivityConfig,
        )

        # ── Step 1: Generate research team from query ──
        if progress_callback:
            progress_callback("generating_profiles", 0, "Generating research team from query...", current=0, total=3)

        team_gen = ResearchTeamGenerator(LLMClient(usage_scope=simulation_id))
        team_result = team_gen.generate_team(
            query=simulation_requirement,
            team_size=min(max_agents, 8),
        )
        agents = team_result["agents"]  # list[dict]
        research_wf = team_result["research_workflow_config"]  # dict

        state.entities_count = len(agents)
        state.entity_types = list({a.get("research_role", "unknown") for a in agents})

        if progress_callback:
            progress_callback(
                "generating_profiles", 50,
                f"Research team generated: {len(agents)} agents",
                current=1, total=3,
            )

        # ── Step 2: Build SimulationParameters (no graph dependency) ──
        agent_configs = []
        for idx, ag in enumerate(agents):
            agent_configs.append(AgentActivityConfig(
                agent_id=ag.get("agent_id", idx),
                entity_uuid=f"webresearch_{idx}",
                entity_name=ag.get("entity_name", ag.get("agent_name", f"Agent-{idx}")),
                entity_type=ag.get("entity_type", "researcher"),
                activity_level=0.8,
                role=ag.get("research_role", "explorer"),
                skills=ag.get("skills", []),
                qualification_score=ag.get("qualification_score", 0.85),
                source_origin="web_research_team",
                research_focus=ag.get("skills", []),
            ))

        # Reconstruct a ResearchWorkflowConfig from the dict
        rwf = ResearchWorkflowConfig(
            workflow_type=research_wf.get("workflow_type", "web_research_csi"),
            mode_label="Web Research / CSI",
            research_rounds=research_wf.get("research_rounds", []),
            claim_policy=research_wf.get("claim_policy", {}),
            debate_policy=research_wf.get("debate_policy", {}),
            verdict_policy=research_wf.get("verdict_policy", {}),
            provenance_policy=research_wf.get("provenance_policy", {}),
            gate_policy=research_wf.get("gate_policy", {}),
        )
        # Build agent_assignments from the team
        for ag in agents:
            rwf.agent_assignments.append(ResearchAgentAssignment(
                agent_id=ag.get("agent_id", 0),
                entity_uuid=f"webresearch_{ag.get('agent_id', 0)}",
                entity_name=ag.get("entity_name", ag.get("agent_name", "")),
                entity_type=ag.get("entity_type", "researcher"),
                research_role=ag.get("research_role", "explorer"),
                responsibility=ag.get("responsibility", ""),
                evidence_priority=ag.get("evidence_priority", "source_diversity"),
                challenge_targets=ag.get("challenge_targets", []),
                output_types=ag.get("world_actions", []) + ag.get("peer_actions", []),
            ))

        sim_params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=state.project_id,
            graph_id="",  # no graph for web research
            simulation_requirement=simulation_requirement,
            config_mode="web_research",
            mode_label="Web Research (query-only)",
            time_config=TimeSimulationConfig(
                total_simulation_hours=1,
                minutes_per_round=60,
            ),
            agent_configs=agent_configs,
            event_config=EventConfig(
                hot_topics=[simulation_requirement],
            ),
            research_workflow_config=rwf,
            generation_reasoning="Web-research mode: team generated from query, no graph dependency",
        )

        # Save config
        config_path = os.path.join(sim_dir, "simulation_config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(sim_params.to_json())

        state.config_reasoning = sim_params.generation_reasoning
        state.config_generated = True
        state.profiles_generated = True
        state.profiles_count = len(agents)

        if progress_callback:
            progress_callback("generating_config", 80, "Saving configuration...", current=2, total=3)

        # ── Step 3: Build profiles payload & initialize CSI store ──
        profiles_payload = agents  # already list[dict] from ResearchTeamGenerator

        # Write empty platform profile files so _check_simulation_prepared passes
        empty_reddit_path = os.path.join(sim_dir, "reddit_profiles.json")
        with open(empty_reddit_path, 'w', encoding='utf-8') as f:
            json.dump(profiles_payload, f, ensure_ascii=False, indent=2)

        empty_twitter_path = os.path.join(sim_dir, "twitter_profiles.csv")
        with open(empty_twitter_path, 'w', encoding='utf-8') as f:
            f.write("agent_id,agent_name,bio\n")
            for ag in agents:
                name = ag.get("agent_name", "").replace(",", " ")
                bio = ag.get("bio", "").replace(",", " ").replace("\n", " ")
                f.write(f"{ag.get('agent_id', 0)},{name},{bio}\n")

        if progress_callback:
            progress_callback("building_csi", 0, "Initializing CSI store for web research...", current=0, total=1)

        csi_store = SimulationCSILocalStore()
        sim_config_dict = sim_params.to_dict()
        csi_store._write_json(
            os.path.join(sim_dir, "csi", "simulation_config_snapshot.json"),
            sim_config_dict,
        )
        csi_store._write_json(
            os.path.join(sim_dir, "csi", "profiles_snapshot.json"),
            profiles_payload,
        )
        csi_result = csi_store.initialize_from_prepare(
            simulation_id=simulation_id,
            project_id=state.project_id,
            graph_id="",
            simulation_requirement=simulation_requirement,
            document_text=document_text or "",
            simulation_config=sim_config_dict,
            profiles=profiles_payload,
            bootstrap_rounds=0,
        )

        state.csi_initialized = True
        state.csi_rounds = csi_result.get("state", {}).get("round_count", 0)
        state.csi_artifacts_ready = True

        if progress_callback:
            progress_callback("building_csi", 100, "CSI store initialized for web research", current=1, total=1)

        # ── Step 4: Check for existing blueprint OR run lightweight seed search ──
        existing_blueprint = None
        try:
            from .csi_research_engine import CSIResearchEngine
            existing_blueprint = CSIResearchEngine.load_blueprint(csi_store, simulation_id)
        except Exception:
            pass

        if existing_blueprint:
            logger.info(
                "Reusing existing blueprint for %s: %d claims, %d sources",
                simulation_id,
                existing_blueprint.get("total_claims", 0),
                existing_blueprint.get("total_sources", 0),
            )
            if progress_callback:
                progress_callback(
                    "collecting_sources", 100,
                    f"Blueprint loaded: {existing_blueprint.get('total_claims', 0)} claims, "
                    f"{existing_blueprint.get('total_sources', 0)} sources from prior run",
                    current=1, total=1,
                )
        else:
            # No prior blueprint — run a lightweight seed search
            if progress_callback:
                progress_callback("collecting_sources", 0, "Running baseline seed search...", current=0, total=1)

            try:
                from .web_search_client import WebSearchClient

                seed_quality_config = {
                    "min_content_length": 200,
                    "min_title_length": 10,
                    "min_search_score": 0.4,
                    "require_news_indicators": False,  # Relaxed for seed — just get context
                    "strict_domain_filter": True,
                    "max_ad_indicators": 2,
                    "english_only": True,
                }

                web_client = WebSearchClient(
                    api_key=Config.TAVILY_API_KEY,
                    quality_config=seed_quality_config,
                )

                if web_client.is_available():
                    # 1-2 broad seed queries derived from the simulation requirement
                    seed_queries = [
                        simulation_requirement[:120],
                        f"{simulation_requirement[:60]} latest research overview",
                    ]

                    existing_sources = csi_result.get("sources", []) or csi_store._load_sources_index(simulation_id).get("sources", [])
                    existing_ids = {s.get("source_id") for s in existing_sources}
                    seed_count = 0

                    for sq in seed_queries:
                        csi_sources = web_client.search_as_csi_sources(
                            query=sq,
                            agent_name="SeedSearch",
                            round_num=0,
                            max_results=5,
                            search_depth="basic",
                        )
                        for src in csi_sources:
                            sid = src.get("source_id", "")
                            if sid not in existing_ids:
                                existing_sources.append(src)
                                existing_ids.add(sid)
                                seed_count += 1

                    # Persist seed sources to the CSI store
                    if seed_count > 0:
                        try:
                            idx = csi_store._load_sources_index(simulation_id)
                            idx_sources = idx.get("sources", [])
                            idx_sources.extend([s for s in existing_sources if s.get("source_id") not in {x.get("source_id") for x in idx_sources}])
                            idx["sources"] = idx_sources
                            idx["source_count"] = len(idx_sources)
                            csi_store._save_sources_index(simulation_id, idx)
                        except Exception as exc:
                            logger.warning("Failed to persist seed sources: %s", exc)

                    if seed_count <= 0:
                        logger.warning(
                            "Seed search produced 0 sources for %s — agents will search reactively during debate",
                            simulation_id,
                        )
                        if progress_callback:
                            progress_callback(
                                "collecting_sources",
                                100,
                                "No seed sources found; agents will search reactively during debate.",
                                current=1,
                                total=1,
                            )

                    logger.info("Seed search complete: %d sources ingested for %s", seed_count, simulation_id)

                    if progress_callback:
                        progress_callback(
                            "collecting_sources",
                            100,
                            f"Seed search done: {seed_count} sources. Agents will search reactively during debate.",
                            current=1,
                            total=1,
                        )
                else:
                    logger.warning("Web search unavailable for %s — Tavily and HIVEMIND Core both unconfigured. Agents will proceed without seed sources.", simulation_id)
                    if progress_callback:
                        progress_callback(
                            "collecting_sources",
                            100,
                            "Web search unavailable — proceeding without seed sources",
                            current=1,
                            total=1,
                        )

            except Exception as exc:
                logger.warning("Seed search failed during prepare (non-fatal): %s", exc)
                if progress_callback:
                    progress_callback(
                        "collecting_sources",
                        100,
                        "Seed search encountered errors — agents will search reactively",
                        current=1,
                        total=1,
                    )

        state.status = SimulationStatus.READY
        self._save_simulation_state(state)
        logger.info(
            "Web-research prepare complete: %s, agents=%d",
            simulation_id, len(agents),
        )
        return state

    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """获取模拟状态"""
        return self._load_simulation_state(simulation_id)

    def _resolve_simulation_requirement(self, state: SimulationState) -> str:
        """Best-effort read of the active research query across state/config/project."""
        if state.simulation_requirement:
            return state.simulation_requirement

        config = self.get_simulation_config(state.simulation_id) or {}
        config_requirement = str(config.get("simulation_requirement") or "").strip()
        if config_requirement:
            return config_requirement

        project = ProjectManager.get_project(state.project_id) if state.project_id else None
        return str(project.simulation_requirement or "").strip() if project else ""

    def _save_simulation_config(self, simulation_id: str, config: Dict[str, Any]) -> None:
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def save_checkpoint(self, simulation_id: str) -> Dict[str, Any]:
        """Save a checkpoint of the current simulation before a continuation run."""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"模拟不存在: {simulation_id}")

        csi_state = SimulationCSILocalStore().get_state(simulation_id)
        round_reached = int(state.current_round or 0)
        round_reached = max(round_reached, int(csi_state.get("round_count", 0) or 0))
        try:
            from .simulation_runner import SimulationRunner
            run_state = SimulationRunner.get_run_state(simulation_id)
            if run_state:
                round_reached = max(round_reached, int(run_state.current_round or 0))
                round_reached = max(round_reached, int(run_state.csi_research_current_round or 0))
        except Exception:
            pass

        checkpoint = {
            "id": f"cp_{len(state.checkpoints) + 1:03d}",
            "query": self._resolve_simulation_requirement(state),
            "timestamp": datetime.now().isoformat(),
            "round_reached": round_reached,
            "artifact_summary": {
                "claims": int(csi_state.get("claim_count", 0) or 0),
                "sources": int(csi_state.get("source_count", 0) or 0),
                "trials": int(csi_state.get("trial_count", 0) or 0),
                "relations": int(csi_state.get("relation_count", 0) or 0),
                "recalls": int(csi_state.get("recall_count", 0) or 0),
                "actions": int(csi_state.get("agent_action_count", 0) or 0),
            },
        }

        state.checkpoints.append(checkpoint)
        self._save_simulation_state(state)
        logger.info("保存模拟检查点: %s (%s)", checkpoint["id"], simulation_id)
        return checkpoint

    def continue_simulation(self, simulation_id: str, new_query: str) -> Dict[str, Any]:
        """Continue a prepared/completed simulation with a new query while preserving CSI artifacts."""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"模拟不存在: {simulation_id}")

        try:
            from .simulation_runner import SimulationRunner
            run_state = SimulationRunner.get_run_state(simulation_id)
            if run_state:
                runner_status = str(run_state.runner_status.value if hasattr(run_state.runner_status, 'value') else run_state.runner_status)
                if runner_status == 'completed' and state.status != SimulationStatus.COMPLETED:
                    state.status = SimulationStatus.COMPLETED
                    self._save_simulation_state(state)
                elif runner_status == 'stopped' and state.status != SimulationStatus.STOPPED:
                    state.status = SimulationStatus.STOPPED
                    self._save_simulation_state(state)
                elif runner_status == 'failed' and state.status != SimulationStatus.FAILED:
                    state.status = SimulationStatus.FAILED
                    self._save_simulation_state(state)
        except Exception:
            pass

        allowed_statuses = {SimulationStatus.READY, SimulationStatus.STOPPED, SimulationStatus.COMPLETED}
        if state.status not in allowed_statuses:
            raise ValueError(f"当前状态为 {state.status.value}，仅已完成或可运行的模拟支持继续提问")

        query = str(new_query or "").strip()
        if not query:
            raise ValueError("query is required")

        checkpoint = self.save_checkpoint(simulation_id)

        state = self._load_simulation_state(simulation_id)
        state.simulation_requirement = query
        state.current_round = 0
        state.status = SimulationStatus.READY
        state.error = None
        self._save_simulation_state(state)

        from .simulation_runner import SimulationRunner

        SimulationRunner.reset_run_state(simulation_id)

        config = self.get_simulation_config(simulation_id)
        if config:
            config["simulation_requirement"] = query
            config["checkpoints"] = state.checkpoints
            self._save_simulation_config(simulation_id, config)

        project = ProjectManager.get_project(state.project_id) if state.project_id else None
        if project:
            project.simulation_requirement = query
            ProjectManager.save_project(project)

        logger.info("继续模拟: %s -> %s", simulation_id, query[:120])
        return {
            "checkpoint_id": checkpoint["id"],
            "previous_query": checkpoint["query"],
            "new_query": query,
            "artifacts_carried": checkpoint["artifact_summary"],
            "checkpoints": state.checkpoints,
        }
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """列出所有模拟"""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # 跳过隐藏文件（如 .DS_Store）和非目录文件
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue
                
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        return simulations
    
    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        """获取模拟的Agent Profile"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"模拟不存在: {simulation_id}")
        
        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")
        
        if not os.path.exists(profile_path):
            return []
        
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """获取模拟配置"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """获取运行说明"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. 激活conda环境: conda activate MiroFish\n"
                f"2. 运行模拟 (脚本位于 {scripts_dir}):\n"
                f"   - 单独运行Twitter: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - 单独运行Reddit: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - 并行运行双平台: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
