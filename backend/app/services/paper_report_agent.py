import json
import re
from typing import Dict, Any, List, Optional, Callable
from .report_agent import ReportAgent, ReportOutline, ReportSection, ReportStatus
from .report_agent import REPORT_WRITING_STYLE_GUIDE, REPORT_CONSUMER_RESEARCH_GUIDE
from ..utils.logger import get_logger

logger = get_logger('mirofish.paper_report_agent')

IEEE_PLAN_SYSTEM_PROMPT = """\
You are a senior academic researcher composing a formal technical research report.
Your task is to plan the outline for a polished paper-style report based on the research query.

【Task】
Generate a logical IEEE-style paper outline in JSON format.

【Research Focus】
Query: {simulation_requirement}

【Paper Structure Requirements】
1. Keep the outline focused on the user's request and the final report outcome.
2. Include, where relevant and in this order: Abstract, Background, Key Findings, Detailed Analysis, Risks / Limitations, Recommendations, References.
3. Keep the outline technical, concise, and evidence-driven.
4. Do not invent unnecessary sections.

【Output Format】
Return ONLY a valid JSON object matching this exact structure:
{{
  "title": "A precise IEEE-style technical title",
  "summary": "A compact abstract summarizing the paper",
  "sections": [
    {{
      "title": "Abstract",
      "description": "What this section will cover"
    }}
  ]
}}
"""

IEEE_SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert academic researcher writing a formal technical research report.
You are currently writing section: **{section_title}**

【Paper Title】
{report_title}

【Abstract / Summary】
{report_summary}

【Research Focus】
{simulation_requirement}

【Previously Written Sections】
{previous_content}

【Research Notes】
{evidence_digest}

【Writing Instructions】
1. Write this section with IEEE-like rigor, concision, and technical precision.
2. Integrate findings precisely. Use concrete data, statistics, and examples.
3. Use normal academic citations in the form [1], [2], [3] that refer to the References section. Do not use hidden tags, internal markers, or system-specific notation.
4. Do not mention internal workflow details, implementation details, agents, claims, trials, or the mechanism used to gather evidence.
5. If this is the References section, list only sourced references in consistent academic style.
6. If there are contradictions or divergent datasets, analyze them objectively without meta-commentary about the process.
7. Write in continuous Markdown format. Use rigorous paragraphs, heading hierarchies (##, ###). NO generic filler.

{writing_style_guide}
"""

class PaperReportAgent(ReportAgent):
    """
    Paper Report Agent - 专注于生成学术/深度研究报告版本
    继承自ReportAgent，但章节生成走直接写作路径，不使用工具回环。
    """

    def _build_ieee_references(self, max_items: int = 12) -> str:
        """Build a real reference list from local CSI sources when available."""
        try:
            from .simulation_csi_local import SimulationCSILocalStore

            store = SimulationCSILocalStore()
            snapshot = store.get_snapshot(self.simulation_id)
            sources = snapshot.get("sources_index", {}).get("sources", []) or []
        except Exception as exc:
            logger.warning("Unable to load CSI sources for references: %s", exc)
            sources = []

        lines = ["## References", ""]
        if not sources:
            lines.append("- [1] No source records were available for this report.")
            return "\n".join(lines)

        for idx, src in enumerate(sources[:max_items], start=1):
            title = str(src.get("title") or src.get("url") or f"Source {idx}").strip()
            origin = str(src.get("origin") or src.get("source_type") or "CSI source").strip()
            url = str(src.get("url") or "").strip()
            summary = str(src.get("summary") or src.get("content") or "").strip()
            summary = summary[:180].replace("\n", " ")
            ref = f"- [{idx}] {title}. {origin}"
            if summary:
                ref += f". {summary}"
            if url:
                ref += f" {url}"
            lines.append(ref)

        return "\n".join(lines)

    def _build_ieee_evidence_digest(
        self,
        section_title: str,
        previous_sections: List[str],
        max_claims: int = 6,
        max_sources: int = 6,
        max_trials: int = 4,
    ) -> str:
        """Build a compact evidence digest from the local snapshot."""
        try:
            from .simulation_csi_local import SimulationCSILocalStore

            store = SimulationCSILocalStore()
            snapshot = store.get_snapshot(self.simulation_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to load CSI snapshot for IEEE digest: %s", exc)
            snapshot = {}

        sources = snapshot.get("sources_index", {}).get("sources", []) or []
        claims = snapshot.get("claims", []) or []
        trials = snapshot.get("trials", []) or []
        state = snapshot.get("state", {}) or {}

        def _short(text: Any, limit: int = 180) -> str:
            value = str(text or "").strip().replace("\n", " ")
            return value[:limit] + ("..." if len(value) > limit else "")

        digest_lines = [
            f"Section focus: {section_title}",
            f"Simulation requirement: {self.simulation_requirement}",
            (
                "Evidence counts: "
                f"sources={state.get('source_count', len(sources))}, "
                f"claims={state.get('claim_count', len(claims))}, "
                f"trials={state.get('trial_count', len(trials))}, "
                f"relations={state.get('relation_count', len(snapshot.get('relations', []) or []))}"
            ),
        ]

        if previous_sections:
            digest_lines.append("Prior sections already written:")
            for prev in previous_sections[-3:]:
                digest_lines.append(f"- {_short(prev, 160)}")

        if sources:
            digest_lines.append("Relevant sources:")
            for idx, src in enumerate(sources[:max_sources], start=1):
                src_id = src.get("source_id") or f"source_{idx}"
                title = _short(src.get("title") or src.get("url") or src_id, 140)
                summary = _short(src.get("summary") or src.get("content") or "", 180)
                digest_lines.append(f"- [{src_id}] {title} :: {summary}")

        if claims:
            digest_lines.append("Verified findings:")
            sorted_claims = sorted(
                claims,
                key=lambda item: (
                    str(item.get("status", "")),
                    -float(item.get("confidence", 0.0) or 0.0),
                    str(item.get("created_at", "")),
                ),
                reverse=True,
            )
            for claim in sorted_claims[:max_claims]:
                claim_id = claim.get("claim_id") or "unknown_claim"
                text = _short(claim.get("text") or claim.get("claim") or "", 220)
                confidence = float(claim.get("confidence", 0.0) or 0.0)
                status = claim.get("status", "proposed")
                source_ids = claim.get("source_ids") or []
                digest_lines.append(
                    f"- [{claim_id}] status={status}, confidence={confidence:.2f}, sources={source_ids}: {text}"
                )

        if trials:
            digest_lines.append("Representative verification notes:")
            for trial in trials[:max_trials]:
                trial_id = trial.get("trial_id") or "unknown_trial"
                verdict = trial.get("verdict", "needs_revision")
                query = _short(trial.get("query") or "", 140)
                response = _short(trial.get("response") or "", 180)
                digest_lines.append(f"- [{trial_id}] verdict={verdict}, query={query}, response={response}")

        return "\n".join(digest_lines).strip()
    
    def plan_outline(
        self,
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
    ) -> Optional[ReportOutline]:
        """Plan the report outline for the topic-focused paper."""
        logger.info(f"开始规划报告大纲: simulation_id={self.simulation_id}")
        
        if self.report_logger:
            self.report_logger.log_planning_start()

        if progress_callback:
            progress_callback("planning", 0, "正在分析模拟需求...")
        
        system_prompt = IEEE_PLAN_SYSTEM_PROMPT.format(
            simulation_requirement=self.simulation_requirement
        )
        
        # 调用大模型生成JSON格式的大纲
        logger.info(f"调用LLM规划大纲: {self.simulation_requirement}")
        if progress_callback:
            progress_callback("planning", 30, "正在生成报告大纲...")
        response_text = self.llm.chat(
            messages=[{"role": "user", "content": system_prompt}],
            response_format={"type": "json_object"}
        )
        
        try:
            outline_dict = json.loads(response_text)
            
            if self.report_logger:
                self.report_logger.log_planning_complete(outline_dict)
                
            outline = ReportOutline.from_dict(outline_dict)
            logger.info(f"大纲规划成功: 标题='{outline.title}', 包含 {len(outline.sections)} 个小节")
            if progress_callback:
                progress_callback("planning", 100, "大纲规划完成")
            return outline
            
        except Exception as e:
            logger.error(f"解析大纲JSON失败: {e}\n原文: {response_text}")
            if self.report_logger:
                self.report_logger.log(
                    action="planning_failed",
                    stage="planning",
                    details={"error": str(e), "raw_response": response_text}
                )
            
            # 使用默认的学术结构如果失败
            return ReportOutline(
            title=f"Technical Report: {self.simulation_requirement[:30]}...",
            summary="A concise technical abstract based on the collected research material.",
            sections=[
                    ReportSection(title="Abstract", content=""),
                    ReportSection(title="Background", content=""),
                    ReportSection(title="Key Findings", content=""),
                    ReportSection(title="Detailed Analysis", content=""),
                    ReportSection(title="Risks / Limitations", content=""),
                    ReportSection(title="Recommendations", content=""),
                    ReportSection(title="References", content=""),
                ]
            )

    def _generate_section_react(
        self,
        outline: ReportOutline,
        section: ReportSection,
        previous_sections: List[str],
        progress_callback: Callable = None,
        section_index: int = None
    ) -> str:
        """Generate section prose directly from the local research material."""
        logger.info(f"章节生成: {section.title}")
        
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
            
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "（这是第一个章节）"
        
        if section.title.strip().lower() == "references":
            return self._build_ieee_references()

        evidence_digest = self._build_ieee_evidence_digest(
            section_title=section.title,
            previous_sections=previous_sections,
        )

        system_prompt = IEEE_SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            previous_content=previous_content,
            evidence_digest=evidence_digest,
            writing_style_guide=REPORT_WRITING_STYLE_GUIDE
        )
        
        user_prompt = (
            f"Write the {section.title} section as clean Markdown. "
            f"Use the research notes above. "
            f"Keep the section grounded in the user request and the collected sources."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response_text = self.llm.chat(
            messages=messages,
            temperature=0.35,
            max_tokens=2800,
        )

        if response_text is None:
            logger.warning(f"章节 {section.title} LLM 返回 None，使用保底草稿")
            response_text = (
                f"## {section.title}\n\n"
                f"This section synthesizes the available research material for {section.title.lower()}."
            )

        if self.report_logger:
            self.report_logger.log_llm_response(
                section_title=section.title,
                section_index=section_index,
                response=response_text,
                iteration=1,
                has_tool_calls=False,
                has_final_answer=False,
            )

        final_answer = self._finalize_section_content(response_text, section.title)
        logger.info(f"章节 {section.title} 生成完毕（IEEE direct mode）")
        return final_answer
