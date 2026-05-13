"""Expert chat service — POV conversations with simulation agents.

Loads an agent's persona, the claims they proposed, the reviews they wrote, and
the sources they cited from the CSI bundle, then drives a conversational LLM
that stays in-character and answers strictly from those artifacts.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


_SIMULATIONS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
    "simulations",
)


def _sim_dir(simulation_id: str) -> str:
    return os.path.join(_SIMULATIONS_ROOT, simulation_id)


def _csi_dir(simulation_id: str) -> str:
    return os.path.join(_sim_dir(simulation_id), "csi")


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def _load_profile(simulation_id: str, agent_id: Any) -> Optional[Dict[str, Any]]:
    profiles_path = os.path.join(_sim_dir(simulation_id), "reddit_profiles.json")
    profiles = _read_json(profiles_path, default=[])
    if not isinstance(profiles, list):
        return None
    target_id = str(agent_id)
    for p in profiles:
        if str(p.get("agent_id")) == target_id or str(p.get("entity_uuid")) == target_id:
            return p
        if p.get("agent_name") and p["agent_name"] == agent_id:
            return p
    return None


def _agent_claims(simulation_id: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    claims = _read_jsonl(os.path.join(_csi_dir(simulation_id), "claims.jsonl"))
    name = (profile.get("agent_name") or "").strip()
    aid = str(profile.get("agent_id"))
    out = []
    for c in claims:
        proposer = str(c.get("proposer_id") or c.get("agent_id") or c.get("author") or "")
        proposer_name = str(c.get("proposer_name") or c.get("agent_name") or "")
        if proposer == aid or (name and proposer_name == name):
            out.append(c)
    return out


def _agent_reviews(simulation_id: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    reviews = _read_jsonl(os.path.join(_csi_dir(simulation_id), "reviews.jsonl"))
    name = (profile.get("agent_name") or "").strip()
    aid = str(profile.get("agent_id"))
    out = []
    for r in reviews:
        reviewer = str(r.get("reviewer_id") or r.get("agent_id") or "")
        reviewer_name = str(r.get("reviewer_name") or r.get("agent_name") or "")
        if reviewer == aid or (name and reviewer_name == name):
            out.append(r)
    return out


def _agent_sources(
    simulation_id: str, agent_claims: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    sources_idx = _read_json(
        os.path.join(_csi_dir(simulation_id), "sources_index.json"), default={}
    )
    by_id = {}
    for s in sources_idx.get("sources", []) if isinstance(sources_idx, dict) else []:
        sid = s.get("source_id") or s.get("id")
        if sid:
            by_id[str(sid)] = s
    seen, out = set(), []
    for c in agent_claims:
        for sid in (c.get("source_ids") or []):
            sid = str(sid)
            if sid in seen:
                continue
            seen.add(sid)
            if sid in by_id:
                out.append(by_id[sid])
    return out[:25]


def _format_persona_block(profile: Dict[str, Any]) -> str:
    """Compact persona block for system prompt."""
    parts = []
    name = profile.get("agent_name", "Expert")
    title = profile.get("entity_type", "")
    affiliation = profile.get("affiliation", "")
    creds = profile.get("credentials", "")
    yrs = profile.get("years_experience", 0)
    loc = profile.get("location", "")
    langs = profile.get("languages") or []
    persona = profile.get("persona", "")
    perspective = profile.get("signature_perspective", "")
    style = profile.get("communication_style", "")
    notable = profile.get("notable_work") or []

    parts.append(f"You are {name} — {title}.")
    if affiliation:
        parts.append(f"Affiliation: {affiliation}.")
    if creds:
        parts.append(f"Credentials: {creds}.")
    if yrs:
        parts.append(f"{yrs} years of experience.")
    if loc:
        parts.append(f"Based in {loc}.")
    if langs:
        parts.append(f"Languages: {', '.join(langs)}.")
    if persona:
        parts.append(f"Background: {persona}")
    if perspective:
        parts.append(f"Signature perspective: {perspective}")
    if style:
        parts.append(f"Communication style: {style}")
    if notable:
        parts.append("Notable work: " + "; ".join(notable[:3]))
    return "\n".join(parts)


def _format_artifacts_block(
    claims: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
) -> str:
    lines = []
    if claims:
        lines.append(f"## YOUR CLAIMS in this investigation ({len(claims)}):")
        for i, c in enumerate(claims[:15], 1):
            text = (c.get("statement") or c.get("claim_text") or c.get("text") or "")[:280]
            status = c.get("status", "")
            conf = c.get("confidence", "")
            lines.append(f"  C{i} [{status} conf={conf}]: {text}")
    if reviews:
        lines.append(f"\n## YOUR REVIEWS of teammates' claims ({len(reviews)}):")
        for i, r in enumerate(reviews[:10], 1):
            verdict = r.get("verdict") or r.get("decision") or ""
            note = (r.get("notes") or r.get("comment") or r.get("rationale") or "")[:200]
            lines.append(f"  R{i} [{verdict}]: {note}")
    if sources:
        lines.append(f"\n## SOURCES you cited ({len(sources)}):")
        for i, s in enumerate(sources[:15], 1):
            title = (s.get("title") or s.get("name") or "")[:120]
            url = s.get("url") or s.get("source_url") or ""
            lines.append(f"  S{i}: {title} — {url}")
    return "\n".join(lines) if lines else "(No artifacts attributed to this agent yet.)"


def build_expert_context(simulation_id: str, agent_id: Any) -> Dict[str, Any]:
    profile = _load_profile(simulation_id, agent_id)
    if not profile:
        raise ValueError(f"Agent {agent_id} not found in simulation {simulation_id}")
    claims = _agent_claims(simulation_id, profile)
    reviews = _agent_reviews(simulation_id, profile)
    sources = _agent_sources(simulation_id, claims)
    sim_config = _read_json(
        os.path.join(_sim_dir(simulation_id), "simulation_config.json"), default={}
    )
    query = sim_config.get("simulation_requirement", "")
    return {
        "profile": profile,
        "claims": claims,
        "reviews": reviews,
        "sources": sources,
        "research_query": query,
    }


def _system_prompt(ctx: Dict[str, Any]) -> str:
    return (
        _format_persona_block(ctx["profile"])
        + "\n\n## RESEARCH QUESTION\n"
        + ctx.get("research_query", "(unspecified)")
        + "\n\n"
        + _format_artifacts_block(ctx["claims"], ctx["reviews"], ctx["sources"])
        + "\n\n## RULES\n"
        "1. Stay strictly in character — speak as the named expert above.\n"
        "2. Ground every factual statement in the artifacts shown. If asked about something not "
        "covered by your claims/reviews/sources, say so plainly and offer your professional "
        "perspective rather than fabricating evidence.\n"
        "3. Use first person ('I argued...', 'In my review of C3...').\n"
        "4. Keep replies concise and human — paragraph or bullets, not essays.\n"
        "5. Never break character or mention you are an AI."
    )


def generate_intro(simulation_id: str, agent_id: Any) -> Dict[str, Any]:
    ctx = build_expert_context(simulation_id, agent_id)
    llm = LLMClient()
    sys_prompt = _system_prompt(ctx)
    user_prompt = (
        "Open the conversation. Give a short greeting (one line), then a 4-6 sentence "
        "summary of (a) what you investigated, (b) the strongest claims you made and "
        "your confidence level, (c) where you disagreed with teammates, and (d) your "
        "personal point of view on the question. Finish with: 'What would you like to "
        "ask me?'"
    )
    try:
        reply = llm.chat(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            max_tokens=600,
        )
    except Exception as exc:
        logger.error("Expert intro LLM failed: %s", exc)
        name = ctx["profile"].get("agent_name", "Expert")
        reply = (
            f"Hello — I'm {name}. I had trouble loading my full briefing just now. "
            "Ask me anything and I'll answer from what I worked on in this case."
        )
    return {
        "agent": {
            "agent_id": ctx["profile"].get("agent_id"),
            "agent_name": ctx["profile"].get("agent_name"),
            "entity_type": ctx["profile"].get("entity_type"),
            "affiliation": ctx["profile"].get("affiliation"),
        },
        "intro": reply,
        "stats": {
            "claims": len(ctx["claims"]),
            "reviews": len(ctx["reviews"]),
            "sources": len(ctx["sources"]),
        },
    }


def chat(
    simulation_id: str,
    agent_id: Any,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    ctx = build_expert_context(simulation_id, agent_id)
    sys_prompt = _system_prompt(ctx)
    msgs: List[Dict[str, str]] = [{"role": "system", "content": sys_prompt}]
    for h in (history or [])[-12:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_message})
    llm = LLMClient()
    try:
        reply = llm.chat(messages=msgs, temperature=0.6, max_tokens=800)
    except Exception as exc:
        logger.error("Expert chat LLM failed: %s", exc)
        reply = (
            "Apologies — I lost the thread for a moment. Could you rephrase that? "
            "I want to give you an answer grounded in what I actually investigated."
        )
    return {"reply": reply}
