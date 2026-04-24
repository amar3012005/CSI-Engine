"""
Report Agent服务
使用LangChain + Zep实现ReACT模式的模拟报告生成

功能：
1. 根据模拟需求和Zep图谱信息生成报告
2. 先规划目录结构，然后分段生成
3. 每段采用ReACT多轮思考与反思模式
4. 支持与用户对话，在对话中自主调用检索工具
"""

import os
import re
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Report Agent 详细日志记录器
    
    在报告文件夹中生成 agent_log.jsonl 文件，记录每一步详细动作。
    每行是一个完整的 JSON 对象，包含时间戳、动作类型、详细内容等。
    """
    
    def __init__(self, report_id: str):
        """
        初始化日志记录器
        
        Args:
            report_id: 报告ID，用于确定日志文件路径
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """确保日志文件所在目录存在"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """获取从开始到现在的耗时（秒）"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        记录一条日志
        
        Args:
            action: 动作类型，如 'start', 'tool_call', 'llm_response', 'section_complete' 等
            stage: 当前阶段，如 'planning', 'generating', 'completed'
            details: 详细内容字典，不截断
            section_title: 当前章节标题（可选）
            section_index: 当前章节索引（可选）
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # 追加写入 JSONL 文件
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """记录报告生成开始"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "报告生成任务开始"
            }
        )
    
    def log_planning_start(self):
        """记录大纲规划开始"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "开始规划报告大纲"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """记录规划时获取的上下文信息"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "获取模拟上下文信息",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """记录大纲规划完成"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "大纲规划完成",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """记录章节生成开始"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"开始生成章节: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """记录 ReACT 思考过程"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT 第{iteration}轮思考"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """记录工具调用"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"调用工具: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """记录工具调用结果（完整内容，不截断）"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # 完整结果，不截断
                "result_length": len(result),
                "message": f"工具 {tool_name} 返回结果"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """记录 LLM 响应（完整内容，不截断）"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # 完整响应，不截断
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM 响应 (工具调用: {has_tool_calls}, 最终答案: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """记录章节内容生成完成（仅记录内容，不代表整个章节完成）"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # 完整内容，不截断
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"章节 {section_title} 内容生成完成"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        记录章节生成完成

        前端应监听此日志来判断一个章节是否真正完成，并获取完整内容
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"章节 {section_title} 生成完成"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """记录报告生成完成"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "报告生成完成"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """记录错误"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"发生错误: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent 控制台日志记录器
    
    将控制台风格的日志（INFO、WARNING等）写入报告文件夹中的 console_log.txt 文件。
    这些日志与 agent_log.jsonl 不同，是纯文本格式的控制台输出。
    """
    
    def __init__(self, report_id: str):
        """
        初始化控制台日志记录器
        
        Args:
            report_id: 报告ID，用于确定日志文件路径
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """确保日志文件所在目录存在"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """设置文件处理器，将日志同时写入文件"""
        import logging
        
        # 创建文件处理器
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # 使用与控制台相同的简洁格式
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # 添加到 report_agent 相关的 logger
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # 避免重复添加
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """关闭文件处理器并从 logger 中移除"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """析构时确保关闭文件处理器"""
        self.close()

    def log_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> None:
        """记录工具调用到控制台风格日志。"""
        logger.info("执行工具: %s, 参数: %s", tool_name, parameters)

    def log_tool_result(self, tool_name: str, result: str) -> None:
        """记录工具返回结果摘要到控制台风格日志。"""
        logger.info("工具 %s 执行完成，结果长度: %s", tool_name, len(result or ""))


class ReportStatus(str, Enum):
    """报告状态"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """报告章节"""
    title: str
    content: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportSection":
        return cls(
            title=str(data.get("title", "")).strip(),
            content=str(data.get("content", data.get("description", ""))).strip(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """转换为Markdown格式"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """报告大纲"""
    title: str
    summary: str
    sections: List[ReportSection]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportOutline":
        sections_data = data.get("sections", []) or []
        sections = [
            ReportSection.from_dict(section)
            for section in sections_data
            if isinstance(section, dict) and str(section.get("title", "")).strip()
        ]
        return cls(
            title=str(data.get("title", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            sections=sections,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """完整报告"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    report_type: str = "standard"
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    # Golden Evidence Trail: claim/trial IDs cited during report generation
    golden_trail: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "report_type": self.report_type,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "golden_trail": self.golden_trail or {}
        }


# ═══════════════════════════════════════════════════════════════
# Prompt 模板常量
# ═══════════════════════════════════════════════════════════════

# ── 工具描述 ──

TOOL_DESC_INSIGHT_FORGE = """\
【深度洞察检索 - 强大的检索工具】
这是我们强大的检索函数，专为深度分析设计。它会：
1. 自动将你的问题分解为多个子问题
2. 从多个维度检索模拟图谱中的信息
3. 整合语义搜索、实体分析、关系链追踪的结果
4. 返回最全面、最深度的检索内容

【使用场景】
- 需要深入分析某个话题
- 需要了解事件的多个方面
- 需要获取支撑报告章节的丰富素材

【返回内容】
- 相关事实原文（可直接引用）
- 核心实体洞察
- 关系链分析"""

TOOL_DESC_PANORAMA_SEARCH = """\
【广度搜索 - 获取全貌视图】
这个工具用于获取模拟结果的完整全貌，特别适合了解事件演变过程。它会：
1. 获取所有相关节点和关系
2. 区分当前有效的事实和历史/过期的事实
3. 帮助你了解舆情是如何演变的

【使用场景】
- 需要了解事件的完整发展脉络
- 需要对比不同阶段的舆情变化
- 需要获取全面的实体和关系信息

【返回内容】
- 当前有效事实（模拟最新结果）
- 历史/过期事实（演变记录）
- 所有涉及的实体"""

TOOL_DESC_QUICK_SEARCH = """\
【简单搜索 - 快速检索】
轻量级的快速检索工具，适合简单、直接的信息查询。

【使用场景】
- 需要快速查找某个具体信息
- 需要验证某个事实
- 简单的信息检索

【返回内容】
- 与查询最相关的事实列表"""

TOOL_DESC_INTERVIEW_AGENTS = """\
【深度采访 - 真实Agent采访（双平台）】
调用OASIS模拟环境的采访API，对正在运行的模拟Agent进行真实采访！
这不是LLM模拟，而是调用真实的采访接口获取模拟Agent的原始回答。
默认在Twitter和Reddit两个平台同时采访，获取更全面的观点。

功能流程：
1. 自动读取人设文件，了解所有模拟Agent
2. 智能选择与采访主题最相关的Agent（如学生、媒体、官方等）
3. 自动生成采访问题
4. 调用 /api/simulation/interview/batch 接口在双平台进行真实采访
5. 整合所有采访结果，提供多视角分析

【使用场景】
- 需要从不同角色视角了解事件看法（学生怎么看？媒体怎么看？官方怎么说？）
- 需要收集多方意见和立场
- 需要获取模拟Agent的真实回答（来自OASIS模拟环境）
- 想让报告更生动，包含"采访实录"

【返回内容】
- 被采访Agent的身份信息
- 各Agent在Twitter和Reddit两个平台的采访回答
- 关键引言（可直接引用）
- 采访摘要和观点对比

【重要】需要OASIS模拟环境正在运行才能使用此功能！"""

REPORT_WRITING_STYLE_GUIDE = """\
## Writing quality bar
- Write like a sharp human analyst, not a generic assistant or marketing model
- Preserve meaning and evidence density, but make the prose sound lived-in and deliberate
- Vary sentence length and rhythm naturally; avoid uniformly polished paragraph cadence
- Use specific claims, sources, dates, actors, and mechanisms instead of vague abstractions
- Acknowledge uncertainty when the evidence is mixed or contested
- Use simple constructions when they are clearer: is, are, has, shows, found

## Patterns to avoid
- Inflated significance: pivotal moment, vital role, enduring testament, broader landscape, key turning point
- Superficial -ing clauses: highlighting, underscoring, showcasing, fostering, contributing to
- Promotional tone: vibrant, groundbreaking, rich heritage, profound, seamless, powerful
- Vague attribution: experts say, observers noted, industry reports, some critics argue
- Copula avoidance: serves as, stands as, marks, represents, boasts, features heavily
- Mechanical rhetoric: rule-of-three lists, not just X but Y, at its core, the real question is
- Tutorial signposting: let's dive in, here's what you need to know, now let's explore
- Generic upbeat endings and filler phrases
- Em dash overuse, boldface abuse, and title-case headline style

## Final pass before responding
- Silently ask: what still sounds obviously AI-generated here?
- Revise those lines before you answer
- Only revise narrative prose; do not remove or rewrite required citation brackets, artifact IDs, verdict labels, confidence fields, or the literal Final Answer control phrase
- Do not mention this audit in the output
"""

REPORT_CONSUMER_RESEARCH_GUIDE = """\
## Consumer-level research discipline
- Cover the whole question, not just the most obvious angle
- Include mainstream findings, dissenting views, and unresolved gaps when they matter
- Prefer practical implications, comparisons, timelines, and concrete examples over abstract framing
- Treat shallow-but-relevant evidence as a lead to deepen, not as finished evidence
- Preserve unique details from tool results instead of flattening them into generic summary language
- Make it clear what a non-expert reader should take away from each section

## Perspective expansion to use when relevant
- Comparative view: alternatives, trade-offs, who is stronger or weaker and why
- Timeline view: what changed over time, what is new, what appears durable
- Risk view: what could fail, what remains uncertain, what evidence is missing
- Public response view: how different stakeholders or communities interpret the issue
- Technical detail view: exact claims, parameters, mechanisms, and source-backed specifics
"""

# ── 大纲规划 prompt ──

PLAN_SYSTEM_PROMPT = """\
You are a senior analyst composing an authoritative **Deep Research Report** powered by Cognitive Swarm Intelligence (CSI).

You have a god-level view of a multi-agent simulation whose swarm of specialist nodes conducted
systematic web research, proposed claims, engaged in peer review, and reached emergent consensus —
mirroring the AgentScope Deep Research architecture of Task Decomposition + Deep Search + Self-Reflection + Synthesis.

## Role
- Evidence-first: every section must be anchored in peer-reviewed CSI Claims, Trials, and Source provenance
- Structured like an analytical intelligence brief, NOT a social media digest
- 4 to 6 sections; each section title is a crisp analytical headline
- Summary = one sharp thesis sentence capturing the core CSI swarm finding

{writing_style_guide}
 
 {consumer_research_guide}

## Outline writing rules
- Section titles must be specific, restrained, and in sentence case
- Avoid inflated or cinematic headings like "A pivotal moment", "The evolving landscape", or "Future outlook"
- Prefer concrete analytical frames such as evidence gaps, consensus patterns, contradictory claims, causal drivers, source provenance, institutional response
- The summary sentence should sound like a human analyst wrote it, not a press release
 - Design sections that would be useful to a smart non-expert reader, not just an internal researcher
 - Make room for at least one section that handles contradiction, uncertainty, comparison, or practical implications when the evidence supports it

## Recommended Section Types:
1. **State of the Simulation Landscape** — scope, agents, sources ingested, evidence density
2. **Agent Dynamics and Knowledge Construction** — search strategy, claim proposal, debate, revision
3. **Emergent Consensus** — high-confidence findings independently endorsed by multiple agents
4. **Divergent Narratives & Contradictions** — contested claims, agent disagreements, unresolved disputes
5. **Evidence Trail & Source Provenance** — tracing key claims back to web sources with citation IDs
6. **Risk Assessment & Future Trends** — structured risk taxonomy with prevention/mitigation strategies

Output JSON in EXACTLY this format:
{{
    "title": "Deep Research Report: Cognitive Swarm Intelligence Analysis of <Topic>",
    "summary": "One-sentence thesis capturing the core CSI finding",
    "sections": [
        {{
            "title": "Section headline",
            "description": "What this section covers and which CSI tools to prioritize"
        }}
    ]
}}

IMPORTANT: sections must be 4 to 6 elements. Fewer than 4 is insufficient depth."""

PLAN_USER_PROMPT_TEMPLATE = """\
## Research Objective
{simulation_requirement}

## Simulation Scale (CSI Swarm Parameters)
- Total entities in simulation graph: {total_nodes}
- Total relationship / knowledge edges: {total_edges}
- Entity type distribution: {entity_types}
- Active specialist agent nodes: {total_entities}

## Sample CSI Claims (partial — from the swarm's research output)
{related_facts_json}

## Your Task
Design the optimal analytical outline for this Deep Research Report. Consider:
1. What core knowledge and event chains did the CSI swarm uncover?
2. Where did agents reach high-confidence consensus vs. contested disagreement?
3. What structured risk taxonomy and future trend analysis would be most valuable?

REMINDER: You MUST output 4 to 6 sections. Fewer is insufficient depth."""

HEALTH_PLAN_SYSTEM_PROMPT = """\
You are a senior clinical analyst composing an evidence-based medical assessment report from CSI simulation outputs.

## Role
- Produce a structured medical report suitable for specialist review.
- Prioritize patient safety, diagnostic reasoning, and evidence provenance.
- Keep section titles concrete and clinically useful.

{writing_style_guide}

## Output requirements
- Return strict JSON only.
- 5 to 6 sections.
- The outline should map to this shape:
  1) Case presentation and clinical context
  2) Differential diagnosis and confidence ranking
  3) Recommended investigations and rationale
  4) Management plan and safety risks
  5) Specialist disagreements and resolution
  6) Evidence trail and bibliography quality

Output JSON in EXACTLY this format:
{{
    "title": "Medical Assessment Report: <Topic>",
    "summary": "One-sentence clinical thesis",
    "sections": [
        {{
            "title": "Section headline",
            "description": "What this section must cover"
        }}
    ]
}}
"""

HEALTH_PLAN_USER_PROMPT_TEMPLATE = """\
## Clinical Objective
{simulation_requirement}

## Simulation Scale
- Total entities in simulation graph: {total_nodes}
- Total relationship edges: {total_edges}
- Entity type distribution: {entity_types}
- Active specialist agents: {total_entities}

## Sample findings from the simulation
{related_facts_json}

## Task
Design a clinically structured outline for a final medical assessment report.
Make sure the outline emphasizes:
1. High-confidence diagnoses vs uncertain differentials
2. Investigation and treatment safety priorities
3. Peer-review disagreements among specialists
4. Source quality and provenance
"""

# ── 章节生成 prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are a senior analyst writing one section of an authoritative **Deep Research Report** powered by Cognitive Swarm Intelligence (CSI).

Report: {report_title}
Summary: {report_summary}
Research Objective: {simulation_requirement}
Current Section: {section_title}

═══════════════════════════════════════════════════════════════
## CORE PRINCIPLE
═══════════════════════════════════════════════════════════════

This report is generated from a Cognitive Swarm Intelligence (CSI) simulation.
A swarm of specialized expert nodes performed deep web research, proposed evidence-grounded claims,
conducted peer review trials, and formed emergent consensus — identical to the AgentScope Deep Research pipeline.

Your task:
- Extract and synthesize the swarm's most valuable findings for this section
- Cite specific Claim IDs, Trial verdicts, and source provenance — making findings 100% traceable
- Write at the quality bar of a professional analytical intelligence report

❌ Do NOT write like a news broadcast or social media digest
✅ Write like: a McKinsey research brief, an intelligence assessment, or a systematic review

{writing_style_guide}
 
 {consumer_research_guide}

═══════════════════════════════════════════════════════════════
## MANDATORY RULES
═══════════════════════════════════════════════════════════════

1. **MUST call CSI tools 3-5 times per section** to retrieve verified swarm findings
   - Prioritize: query_claims, query_consensus, query_contradictions, trace_provenance
   - All content must come from tool results — no fabrication

2. **MUST cite artifact IDs inline**
   - Format: `[Claim: csi_claim_XXXX | confidence: 0.92]` after each cited finding
   - Format: `[Trial: trial_XXXX | verdict: supports]` for peer review evidence
   - This creates the golden evidence trail for graph visualization
    - These bracketed citations are machine-readable. Keep the format exact and do not "humanize" them.

3. **MUST include structured analysis elements:**
   - **Key Finding** boxes for high-confidence consensus items
   - Blockquote citations for direct agent claim text: > "claim text..." — [Agent: Name | Claim ID]
   - Risk items formatted as numbered lists with severity labels when in Risk sections
   - Evidence provenance section at the end: "This finding is supported by N sources, traced via claim_id"

4. **Language**: Write in the language of the research objective. Keep technical IDs (claim_id, trial_id) in English.

5. **High information density**: Every paragraph must add new factual content — no padding

6. **Native prose quality**:
    - Default to precise, direct sentences over dramatic framing
    - Use first-person sparingly and only when it clarifies judgment in synthesis sections
    - When evidence is contested, say so plainly instead of smoothing it into false consensus
    - Avoid stock transition phrases and formulaic section closers
 
 7. **Consumer usefulness**:
    - Do not stop at raw findings; explain what they mean in practical terms
    - If one source hints at something important but remains shallow, retrieve more evidence before finalizing
    - Preserve one-off but important details from tool results instead of compressing them away
    - Compare competing interpretations when the simulation contains disagreement or mixed support
    - If evidence is insufficient, say what is missing instead of padding with generic synthesis

═══════════════════════════════════════════════════════════════
## FORMAT RULES
═══════════════════════════════════════════════════════════════

- NO markdown headings (#, ##, ###) — section title is added by system
- USE **bold**, blockquotes (>), numbered/bullet lists, horizontal rules (---) to organize
- Each section should be 400-800 words of dense, analytical prose
- End each section with: "**Evidence Trail**: N claims cited | M trials referenced | K sources"

═══════════════════════════════════════════════════════════════
## PREVIOUS SECTIONS (context)
═══════════════════════════════════════════════════════════════
{previous_content}

═══════════════════════════════════════════════════════════════
## AVAILABLE CSI TOOLS
═══════════════════════════════════════════════════════════════
{tools_description}

**Priority order**: query_consensus → query_claims → query_contradictions → trace_provenance → query_trials

═══════════════════════════════════════════════════════════════
## WORKFLOW
═══════════════════════════════════════════════════════════════

Each reply must do ONLY ONE of:

Option A — Call a tool:
<execute_tool>
{{"name": "tool_name", "parameters": {{"param": "value"}}}}
</execute_tool>

Option B — Output final content (when you have enough evidence):
Start with "Final Answer:" then write the section content.

⚠️ NEVER mix tool calls and Final Answer in the same reply.
⚠️ NEVER fabricate tool results.
⚠️ Before any Final Answer, do one silent anti-AI pass and revise only the prose around the evidence.
⚠️ Keep `Final Answer:` exactly as written when you are done gathering evidence.
═══════════════════════════════════════════════════════════════"""

SECTION_USER_PROMPT_TEMPLATE = """\
Write the section: **{section_title}**

Previous sections:
{previous_content}

Ground every claim in CSI tool results. Include inline citations [Claim: ID | confidence: X.XX].
End with the Evidence Trail summary line."""

HEALTH_SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are writing one section of a clinical medical assessment report.

Report: {report_title}
Summary: {report_summary}
Clinical objective: {simulation_requirement}
Current section: {section_title}

## Requirements
1. Use CSI evidence only; do not fabricate findings.
2. Call CSI tools 2-5 times where needed before finalizing.
3. Include clear confidence, uncertainty, and safety notes.
4. Cite artifact IDs inline using exact format:
    - [Claim: csi_claim_xxx | confidence: 0.85]
    - [Trial: trial_xxx | verdict: supports]
5. Keep the prose concise, clinically structured, and decision-oriented.

{writing_style_guide}

## Format rules
- No markdown headings (#, ##, ###)
- Use bullets/tables style prose where useful
- End with: **Evidence Trail**: N claims cited | M trials referenced | K sources

## Previous sections
{previous_content}

## Available CSI tools
{tools_description}

## Workflow
Option A: tool call only
<execute_tool>
{{"name": "tool_name", "parameters": {{"param": "value"}}}}
</execute_tool>

Option B: final content only
Start with "Final Answer:" and write the section.
"""

HEALTH_SECTION_USER_PROMPT_TEMPLATE = """\
Write the clinical section: **{section_title}**

Previous sections:
{previous_content}

Ground statements in CSI evidence and keep medical safety implications explicit.
End with the Evidence Trail summary line.
"""

# ── ReACT 循环内消息模板 ──

REACT_OBSERVATION_TEMPLATE = """\
Observation（检索结果）:

═══ 工具 {tool_name} 返回 ═══
{result}

═══════════════════════════════════════════════════════════════
已调用工具 {tool_calls_count}/{max_tool_calls} 次（已用: {used_tools_str}）{unused_hint}
- 如果当前结果与章节目标高度相关，但信息仍然偏浅、只给出线索、缺少细节或缺少对立证据，请继续调用工具深入，而不是用泛化语言补齐
- 如果当前结果已经足够支撑一个明确发现，请输出 Final Answer，并保留具体细节、来源和分歧点
- 如果信息充分：以 "Final Answer:" 开头输出章节内容（必须引用上述原文）
- 如果需要更多信息：调用一个工具继续检索
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "【注意】你只调用了{tool_calls_count}次工具，至少需要{min_tool_calls}次。"
    "请再调用工具获取更多模拟数据，然后再输出 Final Answer。{unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "当前只调用了 {tool_calls_count} 次工具，至少需要 {min_tool_calls} 次。"
    "请调用工具获取模拟数据。{unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "工具调用次数已达上限（{tool_calls_count}/{max_tool_calls}），不能再调用工具。"
    '请立即基于已获取的信息，以 "Final Answer:" 开头输出章节内容。'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 你还没有使用过: {unused_list}，建议尝试不同工具获取多角度信息"

REACT_FORCE_FINAL_MSG = "已达到工具调用限制，请直接输出 Final Answer: 并生成章节内容。"

# ── Chat prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
你是一个简洁高效的模拟预测助手。

【背景】
预测条件: {simulation_requirement}

【已生成的分析报告】
{report_content}

【规则】
1. 优先基于上述报告内容回答问题
2. 直接回答问题，避免冗长的思考论述
3. 仅在报告内容不足以回答时，才调用工具检索更多数据
4. 回答要简洁、清晰、有条理

【可用工具】（仅在需要时使用，最多调用1-2次）
{tools_description}

【工具调用格式】
<execute_tool>
{{"name": "工具名称", "parameters": {{"参数名": "参数值"}}}}
</execute_tool>

【回答风格】
- 简洁直接，不要长篇大论
- 使用 > 格式引用关键内容
- 优先给出结论，再解释原因"""

CHAT_OBSERVATION_SUFFIX = "\n\n请简洁回答问题。"


# ═══════════════════════════════════════════════════════════════
# ReportAgent 主类
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - 模拟报告生成Agent

    采用ReACT（Reasoning + Acting）模式：
    1. 规划阶段：分析模拟需求，规划报告目录结构
    2. 生成阶段：逐章节生成内容，每章节可多次调用工具获取信息
    3. 反思阶段：检查内容完整性和准确性
    """
    
    # ── Golden Evidence Trail helpers ──────────────────────────────────────

    @staticmethod
    def _extract_artifact_ids(text: str) -> Dict[str, List[str]]:
        """Extract CSI artifact IDs referenced in the generated text.

        Matches patterns like:
          csi_claim_XXXX, claim_id, trial_XXXX,
          csi_source_web_XXXX, source_id
        Returns dict with keys: claim_ids, trial_ids, source_ids
        """
        claim_ids = list(set(re.findall(r'csi_claim_[a-zA-Z0-9_]+', text)))
        trial_ids = list(set(re.findall(r'(?:trial_|csi_trial_)[a-zA-Z0-9_]+', text)))
        source_ids = list(set(re.findall(r'csi_source_(?:web_|)[a-zA-Z0-9_]+', text)))
        return {
            "claim_ids": claim_ids,
            "trial_ids": trial_ids,
            "source_ids": source_ids,
        }

    # Comms / constants
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # 最大反思轮数
    MAX_REFLECTION_ROUNDS = 3
    
    # 对话中的最大工具调用次数
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        report_type: str = "standard",
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        初始化Report Agent
        
        Args:
            graph_id: 图谱ID
            simulation_id: 模拟ID
            simulation_requirement: 模拟需求描述
            llm_client: LLM客户端（可选）
            zep_tools: Zep工具服务（可选）
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        normalized_report_type = (report_type or "standard").strip().lower()
        self.report_type = normalized_report_type if normalized_report_type in {"standard", "health"} else "standard"
        
        self.llm = llm_client or LLMClient(usage_scope=self.simulation_id)
        self.zep_tools = zep_tools or ZepToolsService()
        
        # 工具定义
        self.tools = self._define_tools()
        
        # 日志记录器（在 generate_report 中初始化）
        self.report_logger: Optional[ReportLogger] = None
        # 控制台日志记录器（在 generate_report 中初始化）
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(
            "ReportAgent 初始化完成: graph_id=%s, simulation_id=%s, report_type=%s",
            graph_id,
            simulation_id,
            self.report_type,
        )
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """定义可用工具。

        When Zep is disabled (local-only mode), the graph search tools
        (insight_forge, panorama_search, quick_search) return empty results.
        In that case we only expose the CSI store tools so the LLM doesn't
        waste iterations on empty searches.
        """
        # Check if CSI artifacts exist for this simulation
        has_csi = False
        try:
            from .simulation_csi_local import SimulationCSILocalStore
            _store = SimulationCSILocalStore()
            has_csi = _store.has_artifacts(self.simulation_id)
        except Exception:
            pass

        zep_enabled = getattr(self.zep_tools, '_zep_enabled', True)

        tools: Dict[str, Dict[str, Any]] = {}

        # Only include graph search tools when Zep is enabled OR no CSI artifacts
        if zep_enabled or not has_csi:
            tools["insight_forge"] = {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "你想深入分析的问题或话题",
                    "report_context": "当前报告章节的上下文（可选，有助于生成更精准的子问题）"
                }
            }
            tools["panorama_search"] = {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "搜索查询，用于相关性排序",
                    "include_expired": "是否包含过期/历史内容（默认True）"
                }
            }
            tools["quick_search"] = {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "搜索查询字符串",
                    "limit": "返回结果数量（可选，默认10）"
                }
            }
            tools["interview_agents"] = {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "采访主题或需求描述（如：'了解学生对宿舍甲醛事件的看法'）",
                    "max_agents": "最多采访的Agent数量（可选，默认5，最大10）"
                }
            }
        # CSI store tools — always available
        tools["query_claims"] = {
            "name": "query_claims",
            "description": (
                "Search claims produced by simulation agents. Claims are evidence-grounded "
                "findings proposed, peer-reviewed, and revised during the simulation. "
                "Filter by status (proposed/revised/synthesized), minimum confidence, or specific agent."
            ),
            "parameters": {
                "status": "Filter by claim status: proposed, revised, synthesized (optional)",
                "min_confidence": "Minimum confidence threshold 0.0-1.0 (optional, default 0.0)",
                "agent_name": "Filter by specific agent name (optional)",
                "limit": "Max results (optional, default 20)"
            }
        }
        tools["query_trials"] = {
            "name": "query_trials",
            "description": (
                "Search peer review trials where agents evaluated each other's claims. "
                "Each trial has a verdict (supports/contradicts/needs_revision) with reasoning."
            ),
            "parameters": {
                "verdict": "Filter by verdict: supports, contradicts, needs_revision (optional)",
                "claim_id": "Get trials for a specific claim (optional)",
                "limit": "Max results (optional, default 20)"
            }
        }
        tools["query_consensus"] = {
            "name": "query_consensus",
            "description": (
                "Find high-confidence findings — claims that multiple agents independently "
                "endorsed. These are the strongest conclusions from the simulation."
            ),
            "parameters": {
                "min_supporting_trials": "Minimum number of supporting trials (default 2)"
            }
        }
        tools["query_contradictions"] = {
            "name": "query_contradictions",
            "description": (
                "Find contested points — claim pairs where agents disagreed. "
                "Important for balanced reporting."
            ),
            "parameters": {}
        }
        tools["trace_provenance"] = {
            "name": "trace_provenance",
            "description": (
                "Trace a specific claim back to its source evidence, peer reviews, and "
                "revision history. Use for deep-dive into a specific finding."
            ),
            "parameters": {
                "claim_id": "The claim ID to trace"
            }
        }

        return tools
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        执行工具调用
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
            report_context: 报告上下文（用于InsightForge）
            
        Returns:
            工具执行结果（文本格式）
        """
        logger.info(f"执行工具: {tool_name}, 参数: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # 广度搜索 - 获取全貌
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # 简单搜索 - 快速检索
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # 深度采访 - 调用真实的OASIS采访API获取模拟Agent的回答（双平台）
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== CSI local store tools ==========

            elif tool_name == "query_claims":
                return self.zep_tools.query_csi_claims(
                    simulation_id=self.simulation_id,
                    status=parameters.get("status"),
                    min_confidence=float(parameters.get("min_confidence", 0.0)),
                    agent_name=parameters.get("agent_name"),
                    limit=int(parameters.get("limit", 20)),
                )

            elif tool_name == "query_trials":
                return self.zep_tools.query_csi_trials(
                    simulation_id=self.simulation_id,
                    verdict=parameters.get("verdict"),
                    claim_id=parameters.get("claim_id"),
                    limit=int(parameters.get("limit", 20)),
                )

            elif tool_name == "query_consensus":
                min_trials = int(parameters.get("min_supporting_trials", 2))
                return self.zep_tools.query_csi_consensus(
                    simulation_id=self.simulation_id,
                    min_supporting_trials=min_trials,
                )

            elif tool_name == "query_contradictions":
                return self.zep_tools.query_csi_contradictions(
                    simulation_id=self.simulation_id,
                )

            elif tool_name == "trace_provenance":
                claim_id = parameters.get("claim_id", "")
                return self.zep_tools.trace_csi_provenance(
                    simulation_id=self.simulation_id,
                    claim_id=claim_id,
                )

            # ========== 向后兼容的旧工具（内部重定向到新工具） ==========
            
            elif tool_name == "search_graph":
                # 重定向到 quick_search
                logger.info("search_graph 已重定向到 quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # 重定向到 insight_forge，因为它更强大
                logger.info("get_simulation_context 已重定向到 insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return (
                    f"未知工具: {tool_name}。请使用以下工具之一: "
                    "insight_forge, panorama_search, quick_search, "
                    "query_claims, query_trials, query_consensus, query_contradictions, trace_provenance"
                )
                
        except Exception as e:
            logger.error(f"工具执行失败: {tool_name}, 错误: {str(e)}")
            return (
                f"工具 {tool_name} 执行失败: {str(e)}\n"
                "请不要再调用此工具，直接根据你已有的信息输出 Final Answer。"
            )

    # 合法的工具名称集合，用于裸 JSON 兜底解析时校验
    VALID_TOOL_NAMES = {
        "insight_forge", "panorama_search", "quick_search", "interview_agents",
        "query_claims", "query_trials", "query_consensus", "query_contradictions",
        "trace_provenance",
    }

    def _normalize_tool_name(self, tool_name: Optional[str]) -> str:
        """Normalize prefixed tool names emitted by providers/models."""
        normalized = str(tool_name or "").strip()
        if normalized.startswith("tool_"):
            normalized = normalized.replace("tool_", "", 1)
        for prefix in ("tool.", "repo."):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        return normalized

    def _extract_action_call_from_string(self, raw_arguments: str) -> Optional[Dict[str, Any]]:
        """Parse textual native tool-call payloads such as assistant Action/Action Input."""
        if not raw_arguments:
            return None

        action_match = re.search(r"Action:\s*([^\n\r]+)", raw_arguments)
        if not action_match:
            return None

        tool_name = self._normalize_tool_name(action_match.group(1))
        if tool_name not in self.VALID_TOOL_NAMES:
            return None

        parameters: Dict[str, Any] = {}
        action_input_match = re.search(r"Action Input:\s*(\{[\s\S]*?\})", raw_arguments)
        if action_input_match:
            input_str = action_input_match.group(1).strip()
            try:
                parameters = json.loads(input_str)
            except json.JSONDecodeError:
                cleaned = input_str.split("</execute_tool>", 1)[0].strip()
                cleaned = cleaned.rstrip("}\n\r\t ") + "}"
                try:
                    parameters = json.loads(cleaned)
                except json.JSONDecodeError:
                    logger.warning("无法从字符串 Action Input 解析 JSON: %s", input_str)

        return {
            "name": tool_name,
            "parameters": parameters,
        }

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        从LLM响应中解析工具调用

        支持的格式（按优先级）：
        1. <execute_tool>{"name": "tool_name", "parameters": {...}}</execute_tool>
        2. 裸 JSON（响应整体或单行就是一个工具调用 JSON）
        """
        tool_calls = []

        # 格式1: XML风格（标准格式）
        xml_pattern = r'<execute_tool>\s*(\{.*?\})\s*</execute_tool>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # 格式2: 兜底 - LLM 直接输出裸 JSON（没包 <execute_tool> 标签）
        # 只在格式1未匹配时尝试，避免误匹配正文中的 JSON
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # 响应可能包含思考文字 + 裸 JSON，尝试提取最后一个 JSON 对象
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """校验解析出的 JSON 是否是合法的工具调用"""
        if not isinstance(data, dict):
            return False

        # Handle native tool call extraction format from LLMClient
        if "arguments" in data and isinstance(data["arguments"], dict):
            args = data["arguments"]
            # case: {"name": "tool_call", "arguments": {"name":"...","parameters":{...}}}
            if data.get("name") == "tool_call" and "name" in args:
                data["name"] = args.get("name")
                data["parameters"] = args.get("parameters", {})
            # case: {"name": "tool_query_claims", "arguments": {"status":"...","min_confidence":...}}
            elif str(data.get("name", "")).startswith("tool_"):
                data["name"] = data["name"].replace("tool_", "", 1)
                data["parameters"] = args
            elif str(data.get("name", "")).startswith(("tool.", "repo.")):
                data["name"] = self._normalize_tool_name(data.get("name"))
                data["parameters"] = args
            # case: {"name": "query_claims", "arguments": {"name":"query_claims","parameters":{...}}}
            elif data.get("name") in self.VALID_TOOL_NAMES and "name" in args and "parameters" in args:
                data["name"] = args["name"]
                data["parameters"] = args["parameters"]
            # case: {"name": "query_claims", "arguments": {"status":"...", ...}}
            elif data.get("name") in self.VALID_TOOL_NAMES:
                data["parameters"] = args
        elif isinstance(data.get("arguments"), str):
            extracted = self._extract_action_call_from_string(data["arguments"])
            if extracted:
                data.update(extracted)

        # 支持 {"name": ..., "parameters": ...} 和 {"tool": ..., "params": ...} 两种键名
        tool_name = self._normalize_tool_name(data.get("name") or data.get("tool"))
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # 统一键名为 name / parameters
            if "tool" in data:
                data.pop("tool")
            data["name"] = tool_name
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """生成工具描述文本"""
        desc_parts = ["可用工具："]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  参数: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        规划报告大纲
        
        使用LLM分析模拟需求，规划报告的目录结构
        
        Args:
            progress_callback: 进度回调函数
            
        Returns:
            ReportOutline: 报告大纲
        """
        logger.info("开始规划报告大纲...")
        
        if progress_callback:
            progress_callback("planning", 0, "正在分析模拟需求...")
        
        # 首先获取模拟上下文
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )

        # Get CSI summary for claims/trials awareness during planning
        csi_summary = self.zep_tools.get_csi_summary(self.simulation_id)

        if progress_callback:
            progress_callback("planning", 30, "正在生成报告大纲...")

        if self.report_type == "health":
            system_prompt = HEALTH_PLAN_SYSTEM_PROMPT.format(
                writing_style_guide=REPORT_WRITING_STYLE_GUIDE,
            )
            user_prompt = HEALTH_PLAN_USER_PROMPT_TEMPLATE.format(
                simulation_requirement=self.simulation_requirement,
                total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
                total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
                entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
                total_entities=context.get('total_entities', 0),
                related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
            )
        else:
            system_prompt = PLAN_SYSTEM_PROMPT
            system_prompt = system_prompt.format(
                writing_style_guide=REPORT_WRITING_STYLE_GUIDE,
                consumer_research_guide=REPORT_CONSUMER_RESEARCH_GUIDE,
            )
            user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
                simulation_requirement=self.simulation_requirement,
                total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
                total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
                entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
                total_entities=context.get('total_entities', 0),
                related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
            )

        # Append CSI summary so the LLM knows what claims/trials exist
        if csi_summary and "No CSI artifacts" not in csi_summary:
            user_prompt += f"\n\n【模拟CSI研究成果概览】\n{csi_summary}"

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "正在解析大纲结构...")
            
            # 解析大纲
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "模拟分析报告"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "大纲规划完成")
            
            logger.info(f"大纲规划完成: {len(sections)} 个章节")
            return outline
            
        except Exception as e:
            logger.error(f"大纲规划失败: {str(e)}")
            # 返回默认大纲（4个章节，作为fallback）
            return ReportOutline(
                title="未来预测报告",
                summary="基于模拟预测的未来趋势与风险分析",
                sections=[
                    ReportSection(title="预测场景与核心发现"),
                    ReportSection(title="关键证据与论点演化"),
                    ReportSection(title="人群行为预测分析"),
                    ReportSection(title="趋势展望与风险提示")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        使用ReACT模式生成单个章节内容
        
        ReACT循环：
        1. Thought（思考）- 分析需要什么信息
        2. Action（行动）- 调用工具获取信息
        3. Observation（观察）- 分析工具返回结果
        4. 重复直到信息足够或达到最大次数
        5. Final Answer（最终回答）- 生成章节内容
        
        Args:
            section: 要生成的章节
            outline: 完整大纲
            previous_sections: 之前章节的内容（用于保持连贯性）
            progress_callback: 进度回调
            section_index: 章节索引（用于日志记录）
            
        Returns:
            章节内容（Markdown格式）
        """
        logger.info(f"ReACT生成章节: {section.title}")
        
        # 记录章节开始日志
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
            
        # 构建用户prompt - 每个已完成章节各传入最大4000字
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # 每个章节最多4000字
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "（这是第一个章节）"
        
        if self.report_type == "health":
            system_prompt = HEALTH_SECTION_SYSTEM_PROMPT_TEMPLATE.format(
                report_title=outline.title,
                report_summary=outline.summary,
                simulation_requirement=self.simulation_requirement,
                section_title=section.title,
                tools_description=self._get_tools_description(),
                previous_content=previous_content,
                writing_style_guide=REPORT_WRITING_STYLE_GUIDE,
            )
            user_prompt = HEALTH_SECTION_USER_PROMPT_TEMPLATE.format(
                previous_content=previous_content,
                section_title=section.title,
            )
        else:
            system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
                report_title=outline.title,
                report_summary=outline.summary,
                simulation_requirement=self.simulation_requirement,
                section_title=section.title,
                tools_description=self._get_tools_description(),
                previous_content=previous_content,
                writing_style_guide=REPORT_WRITING_STYLE_GUIDE,
                consumer_research_guide=REPORT_CONSUMER_RESEARCH_GUIDE,
            )
            user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
                previous_content=previous_content,
                section_title=section.title,
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT循环
        tool_calls_count = 0
        max_iterations = 5  # 最大迭代轮数
        # When Zep is disabled, tools only return local data which may be sparse.
        # Lower the minimum tool call requirement so the agent can finish faster
        # instead of looping on empty results.
        min_tool_calls = 1 if not self.zep_tools._zep_enabled else 3
        conflict_retries = 0  # 工具调用与Final Answer同时出现的连续冲突次数
        used_tools = set()  # 记录已调用过的工具名
        all_tools = set(self.tools.keys())

        # 报告上下文，用于InsightForge的子问题生成
        report_context = f"章节标题: {section.title}\n模拟需求: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"深度检索与撰写中 ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # 调用LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # 检查 LLM 返回是否为 None（API 异常或内容为空）
            if response is None:
                logger.warning(f"章节 {section.title} 第 {iteration + 1} 次迭代: LLM 返回 None")
                # 如果还有迭代次数，添加消息并重试
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "（响应为空）"})
                    messages.append({"role": "user", "content": "请继续生成内容。"})
                    continue
                # 最后一次迭代也返回 None，跳出循环进入强制收尾
                break

            logger.debug(f"LLM响应: {response[:200]}...")

            # 解析一次，复用结果
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── 冲突处理：LLM 同时输出了工具调用和 Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"章节 {section.title} 第 {iteration+1} 轮: "
                    f"LLM 同时输出工具调用和 Final Answer（第 {conflict_retries} 次冲突）"
                )

                if conflict_retries <= 2:
                    # 前两次：丢弃本次响应，要求 LLM 重新回复
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "【格式错误】你在一次回复中同时包含了工具调用和 Final Answer，这是不允许的。\n"
                            "每次回复只能做以下两件事之一：\n"
                            "- 调用一个工具（输出一个 <execute_tool> 块，不要写 Final Answer）\n"
                            "- 输出最终内容（以 'Final Answer:' 开头，不要包含 <execute_tool>）\n"
                            "请重新回复，只做其中一件事。"
                        ),
                    })
                    continue
                else:
                    # 第三次：降级处理，截断到第一个工具调用，强制执行
                    logger.warning(
                        f"章节 {section.title}: 连续 {conflict_retries} 次冲突，"
                        "降级为截断执行第一个工具调用"
                    )
                    first_tool_end = response.find('</execute_tool>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</execute_tool>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # 记录 LLM 响应日志
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── 情况1：LLM 输出了 Final Answer ──
            if has_final_answer:
                # 工具调用次数不足，拒绝并要求继续调工具
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"（这些工具还未使用，推荐用一下他们: {', '.join(unused_tools)}）" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # 正常结束
                final_answer = self._finalize_section_content(
                    response.split("Final Answer:")[-1].strip(),
                    section.title,
                )
                logger.info(f"章节 {section.title} 生成完成（工具调用: {tool_calls_count}次）")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── 情况2：LLM 尝试调用工具 ──
            if has_tool_calls:
                # 工具额度已耗尽 → 明确告知，要求输出 Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # 只执行第一个工具调用
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM 尝试调用 {len(tool_calls)} 个工具，只执行第一个: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # 构建未使用工具提示
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── 情况3：既没有工具调用，也没有 Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # 工具调用次数不足，推荐未用过的工具
                unused_tools = all_tools - used_tools
                unused_hint = f"（这些工具还未使用，推荐用一下他们: {', '.join(unused_tools)}）" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # 工具调用已足够，LLM 输出了内容但没带 "Final Answer:" 前缀
            # 直接将这段内容作为最终答案，不再空转
            logger.info(f"章节 {section.title} 未检测到 'Final Answer:' 前缀，直接采纳LLM输出作为最终内容（工具调用: {tool_calls_count}次）")
            final_answer = self._finalize_section_content(response.strip(), section.title)

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # 达到最大迭代次数，强制生成内容
        logger.warning(f"章节 {section.title} 达到最大迭代次数，强制生成")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # 检查强制收尾时 LLM 返回是否为 None
        if response is None:
            logger.error(f"章节 {section.title} 强制收尾时 LLM 返回 None，使用默认错误提示")
            final_answer = f"（本章节生成失败：LLM 返回空响应，请稍后重试）"
        elif "Final Answer:" in response:
            final_answer = self._finalize_section_content(
                response.split("Final Answer:")[-1].strip(),
                section.title,
            )
        else:
            final_answer = self._finalize_section_content(response, section.title)
        
        # 记录章节内容生成完成日志
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer

    def _finalize_section_content(self, content: Optional[str], section_title: str) -> str:
        """Remove ReACT/tool leakage before persisting section prose."""
        cleaned = self._strip_react_markup(content)
        if cleaned:
            return cleaned

        logger.warning(f"章节 {section_title} 未生成可用正文，写入占位提示")
        return "(This section did not converge to final prose and needs regeneration.)"

    @staticmethod
    def _strip_react_markup(content: Optional[str]) -> str:
        """Strip tool-call scaffolding and return only user-facing markdown."""
        if not content:
            return ""

        cleaned = content.strip()

        cleaned = re.sub(
            r"<execute_tool>.*?</execute_tool>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(r"^\s*Final Answer:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"^\s*(Thought|Action|Action Input|Observation|Partial Draft):.*$",
            "",
            cleaned,
            flags=re.MULTILINE,
        )

        fenced_match = re.match(r"^```(?:markdown|md)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL)
        if fenced_match:
            cleaned = fenced_match.group(1).strip()

        cleaned_lines = [line.rstrip() for line in cleaned.splitlines()]
        while cleaned_lines and not cleaned_lines[0].strip():
            cleaned_lines.pop(0)
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()

        return "\n".join(cleaned_lines).strip()
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        生成完整报告（分章节实时输出）
        
        每个章节生成完成后立即保存到文件夹，不需要等待整个报告完成。
        文件结构：
        reports/{report_id}/
            meta.json       - 报告元信息
            outline.json    - 报告大纲
            progress.json   - 生成进度
            section_01.md   - 第1章节
            section_02.md   - 第2章节
            ...
            full_report.md  - 完整报告
        
        Args:
            progress_callback: 进度回调函数 (stage, progress, message)
            report_id: 报告ID（可选，如果不传则自动生成）
            
        Returns:
            Report: 完整报告
        """
        import uuid
        
        # 如果没有传入 report_id，则自动生成
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            report_type=self.report_type,
            created_at=datetime.now().isoformat()
        )
        
        # 已完成的章节标题列表（用于进度追踪）
        completed_section_titles = []
        
        try:
            # 初始化：创建报告文件夹并保存初始状态
            ReportManager._ensure_report_folder(report_id)
            
            # 初始化日志记录器（结构化日志 agent_log.jsonl）
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # 初始化控制台日志记录器（console_log.txt）
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "初始化报告...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # 阶段1: 规划大纲
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "开始规划报告大纲...",
                completed_sections=[]
            )
            
            # 记录规划开始日志
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "开始规划报告大纲...")

            def _forward_progress(
                stage: str,
                progress: int,
                message: str,
                **_: Any,
            ) -> None:
                if progress_callback:
                    progress_callback(stage, progress, message)
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg, **kwargs:
                    _forward_progress(stage, prog // 5, msg, **kwargs)
            )
            report.outline = outline
            
            # 记录规划完成日志
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # 保存大纲到文件
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"大纲规划完成，共{len(outline.sections)}个章节",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"大纲已保存到文件: {report_id}/outline.json")
            
            # 阶段2: 逐章节生成（分章节保存）
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # 保存内容用于上下文

            # Golden trail sets — accumulate artifact IDs cited in report
            all_claim_ids: set = set()
            all_trial_ids: set = set()
            all_source_ids: set = set()
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # 更新进度
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"正在生成章节: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"正在生成章节: {section.title} ({section_num}/{total_sections})"
                    )
                
                # 生成主章节内容
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg, **kwargs:
                        _forward_progress(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg,
                            **kwargs,
                        ),
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Accumulate golden evidence trail
                section_artifacts = self._extract_artifact_ids(section_content)
                all_claim_ids.update(section_artifacts["claim_ids"])
                all_trial_ids.update(section_artifacts["trial_ids"])
                all_source_ids.update(section_artifacts["source_ids"])

                # 保存章节
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # 记录章节完成日志
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"章节已保存: {report_id}/section_{section_num:02d}.md")
                
                # 更新进度
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"章节 {section.title} 已完成",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # 阶段3: 组装完整报告
            if progress_callback:
                progress_callback("generating", 95, "正在组装完整报告...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "正在组装完整报告...",
                completed_sections=completed_section_titles
            )
            
            # 使用ReportManager组装完整报告
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # 计算总耗时
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # 记录报告完成日志
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Finalize golden trail
            report.golden_trail = {
                "claim_ids": sorted(all_claim_ids),
                "trial_ids": sorted(all_trial_ids),
                "source_ids": sorted(all_source_ids),
                "total_artifacts": len(all_claim_ids) + len(all_trial_ids) + len(all_source_ids),
            }

            # 保存最终报告
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "报告生成完成",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "报告生成完成")
            
            logger.info(f"报告生成完成: {report_id}")
            
            # 关闭控制台日志记录器
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"报告生成失败: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # 记录错误日志
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # 保存失败状态
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"报告生成失败: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # 忽略保存失败的错误
            
            # 关闭控制台日志记录器
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        与Report Agent对话
        
        在对话中Agent可以自主调用检索工具来回答问题
        
        Args:
            message: 用户消息
            chat_history: 对话历史
            
        Returns:
            {
                "response": "Agent回复",
                "tool_calls": [调用的工具列表],
                "sources": [信息来源]
            }
        """
        logger.info(f"Report Agent对话: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # 获取已生成的报告内容
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # 限制报告长度，避免上下文过长
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [报告内容已截断] ..."
        except Exception as e:
            logger.warning(f"获取报告内容失败: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "（暂无报告）",
            tools_description=self._get_tools_description(),
        )

        # 构建消息
        messages = [{"role": "system", "content": system_prompt}]
        
        # 添加历史对话
        for h in chat_history[-10:]:  # 限制历史长度
            messages.append(h)
        
        # 添加用户消息
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT循环（简化版）
        tool_calls_made = []
        max_iterations = 2  # 减少迭代轮数
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # 解析工具调用
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # 没有工具调用，直接返回响应
                clean_response = re.sub(r'<execute_tool>.*?</execute_tool>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # 执行工具调用（限制数量）
            tool_results = []
            for call in tool_calls[:1]:  # 每轮最多执行1次工具调用
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # 限制结果长度
                })
                tool_calls_made.append(call)
            
            # 将结果添加到消息
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']}结果]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # 达到最大迭代，获取最终响应
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # 清理响应
        clean_response = re.sub(r'<execute_tool>.*?</execute_tool>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    报告管理器
    
    负责报告的持久化存储和检索
    
    文件结构（分章节输出）：
    reports/
      {report_id}/
        meta.json          - 报告元信息和状态
        outline.json       - 报告大纲
        progress.json      - 生成进度
        section_01.md      - 第1章节
        section_02.md      - 第2章节
        ...
        full_report.md     - 完整报告
    """
    
    # 报告存储目录
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """确保报告根目录存在"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """获取报告文件夹路径"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """确保报告文件夹存在并返回路径"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """获取报告元信息文件路径"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """获取完整报告Markdown文件路径"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """获取大纲文件路径"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """获取进度文件路径"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """获取章节Markdown文件路径"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """获取 Agent 日志文件路径"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """获取控制台日志文件路径"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        获取控制台日志内容
        
        这是报告生成过程中的控制台输出日志（INFO、WARNING等），
        与 agent_log.jsonl 的结构化日志不同。
        
        Args:
            report_id: 报告ID
            from_line: 从第几行开始读取（用于增量获取，0 表示从头开始）
            
        Returns:
            {
                "logs": [日志行列表],
                "total_lines": 总行数,
                "from_line": 起始行号,
                "has_more": 是否还有更多日志
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # 保留原始日志行，去掉末尾换行符
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # 已读取到末尾
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        获取完整的控制台日志（一次性获取全部）
        
        Args:
            report_id: 报告ID
            
        Returns:
            日志行列表
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        获取 Agent 日志内容
        
        Args:
            report_id: 报告ID
            from_line: 从第几行开始读取（用于增量获取，0 表示从头开始）
            
        Returns:
            {
                "logs": [日志条目列表],
                "total_lines": 总行数,
                "from_line": 起始行号,
                "has_more": 是否还有更多日志
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # 跳过解析失败的行
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # 已读取到末尾
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        获取完整的 Agent 日志（用于一次性获取全部）
        
        Args:
            report_id: 报告ID
            
        Returns:
            日志条目列表
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        保存报告大纲
        
        在规划阶段完成后立即调用
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"大纲已保存: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        保存单个章节

        在每个章节生成完成后立即调用，实现分章节输出

        Args:
            report_id: 报告ID
            section_index: 章节索引（从1开始）
            section: 章节对象

        Returns:
            保存的文件路径
        """
        cls._ensure_report_folder(report_id)

        # 构建章节Markdown内容 - 清理可能存在的重复标题
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # 保存文件
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"章节已保存: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        清理章节内容
        
        1. 移除内容开头与章节标题重复的Markdown标题行
        2. 将所有 ### 及以下级别的标题转换为粗体文本
        
        Args:
            content: 原始内容
            section_title: 章节标题
            
        Returns:
            清理后的内容
        """
        import re
        
        if not content:
            return content
        
        content = ReportAgent._strip_react_markup(content)
        content = content.strip()

        if not content:
            return ""

        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # 检查是否是Markdown标题行
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # 检查是否是与章节标题重复的标题（跳过前5行内的重复）
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # 将所有级别的标题（#, ##, ###, ####等）转换为粗体
                # 因为章节标题由系统添加，内容中不应有任何标题
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # 添加空行
                continue
            
            # 如果上一行是被跳过的标题，且当前行为空，也跳过
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # 移除开头的空行
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # 移除开头的分隔线
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # 同时移除分隔线后的空行
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        更新报告生成进度
        
        前端可以通过读取progress.json获取实时进度
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """获取报告生成进度"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        获取已生成的章节列表
        
        返回所有已保存的章节文件信息
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 从文件名解析章节索引
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        组装完整报告
        
        从已保存的章节文件组装完整报告，并进行标题清理
        """
        folder = cls._get_report_folder(report_id)
        
        # 构建报告头部
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # 按顺序读取所有章节文件
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # 后处理：清理整个报告的标题问题
        md_content = cls._post_process_report(md_content, outline)
        
        # 保存完整报告
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"完整报告已组装: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        后处理报告内容
        
        1. 移除重复的标题
        2. 保留报告主标题(#)和章节标题(##)，移除其他级别的标题(###, ####等)
        3. 清理多余的空行和分隔线
        
        Args:
            content: 原始报告内容
            outline: 报告大纲
            
        Returns:
            处理后的内容
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # 收集大纲中的所有章节标题
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # 检查是否是标题行
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # 检查是否是重复标题（在连续5行内出现相同内容的标题）
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # 跳过重复标题及其后的空行
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # 标题层级处理：
                # - # (level=1) 只保留报告主标题
                # - ## (level=2) 保留章节标题
                # - ### 及以下 (level>=3) 转换为粗体文本
                
                if level == 1:
                    if title == outline.title:
                        # 保留报告主标题
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # 章节标题错误使用了#，修正为##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # 其他一级标题转为粗体
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # 保留章节标题
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # 非章节的二级标题转为粗体
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### 及以下级别的标题转换为粗体文本
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # 跳过标题后紧跟的分隔线
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # 标题后只保留一个空行
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # 清理连续的多个空行（保留最多2个）
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """保存报告元信息和完整报告"""
        cls._ensure_report_folder(report.report_id)
        
        # 保存元信息JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # 保存大纲
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # 保存完整Markdown报告
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"报告已保存: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """获取报告"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # 兼容旧格式：检查直接存储在reports目录下的文件
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 重建Report对象
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # 如果markdown_content为空，尝试从full_report.md读取
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            report_type=data.get('report_type', 'standard'),
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str, report_type: Optional[str] = None) -> Optional[Report]:
        """根据模拟ID获取报告，可按报告类型过滤。"""
        cls._ensure_reports_dir()

        matches = []
        normalized_type = (report_type or "").strip().lower() or None
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # 新格式：文件夹
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    if normalized_type and (report.report_type or "standard") != normalized_type:
                        continue
                    matches.append(report)
            # 兼容旧格式：JSON文件
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    if normalized_type and (report.report_type or "standard") != normalized_type:
                        continue
                    matches.append(report)

        if not matches:
            return None

        matches.sort(key=lambda report: report.created_at or "", reverse=True)
        return matches[0]
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """列出报告"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # 新格式：文件夹
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # 兼容旧格式：JSON文件
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # 按创建时间倒序
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """删除报告（整个文件夹）"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # 新格式：删除整个文件夹
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"报告文件夹已删除: {report_id}")
            return True
        
        # 兼容旧格式：删除单独的文件
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
