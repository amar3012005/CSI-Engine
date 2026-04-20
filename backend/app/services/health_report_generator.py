"""
Health report generator — builds a comprehensive structured medical report
from CSI simulation artifacts (claims, reviews, sources).

Produces per-agent specialist sections ordered by clinical relevance,
with real source URLs/PMIDs preserved from tavily/groq search results.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("mirofish.health_report_generator")

# Clinical relevance ordering (lower = higher priority in report)
CLINICAL_RELEVANCE_ORDER: Dict[str, int] = {
    "diagnostician": 1,
    "primary_physician": 2,
    "medical_researcher": 3,
    "clinical_pharmacologist": 4,
    "medical_synthesizer": 5,
    "cardiologist": 6,
    "pulmonologist": 7,
    "endocrinologist": 8,
    "neurologist": 9,
    "nephrologist": 10,
    "patient_advocate": 11,
}

# Source domain → tier classification
_TIER1_DOMAINS = {
    "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "cochranelibrary.com", "cochrane.org", "clinicaltrials.gov",
    "who.int", "emro.who.int", "euro.who.int",
}
_TIER2_DOMAINS = {
    "ahajournals.org", "acc.org", "hfsa.org", "jacc.org",
    "nejm.org", "thelancet.com", "bmj.com", "jamanetwork.com",
    "ema.europa.eu", "fda.gov", "drugs.com",
    "e-cmsj.org",
}


def _extract_domain(url: str) -> str:
    m = re.search(r'https?://([^/]+)', url or "")
    return m.group(1).lstrip("www.") if m else ""


def _classify_source_tier(url: str) -> str:
    domain = _extract_domain(url)
    if domain in _TIER1_DOMAINS:
        return "tier1"
    if domain in _TIER2_DOMAINS:
        return "tier2"
    return "tier3"


def _extract_pmid(url: str) -> Optional[str]:
    """Extract PubMed ID from pubmed/pmc URL."""
    m = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', url or "")
    if m:
        return m.group(1)
    m = re.search(r'pmc\.ncbi\.nlm\.nih\.gov/articles/PMC(\d+)', url or "")
    if m:
        return f"PMC{m.group(1)}"
    return None


def _source_label(url: str) -> str:
    domain = _extract_domain(url)
    labels = {
        "pubmed.ncbi.nlm.nih.gov": "PubMed",
        "pmc.ncbi.nlm.nih.gov": "PubMed Central",
        "ncbi.nlm.nih.gov": "NCBI",
        "cochranelibrary.com": "Cochrane Library",
        "clinicaltrials.gov": "ClinicalTrials.gov",
        "who.int": "WHO",
        "ahajournals.org": "AHA Journals",
        "acc.org": "ACC",
        "hfsa.org": "HFSA Guidelines",
        "jacc.org": "JACC",
        "nejm.org": "NEJM",
        "thelancet.com": "The Lancet",
        "bmj.com": "BMJ",
        "jamanetwork.com": "JAMA",
    }
    return labels.get(domain, domain)


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return items


def _load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _csi_dir(simulation_id: str) -> str:
    base = getattr(Config, "OASIS_SIMULATION_DATA_DIR", None) or os.path.join(
        os.path.dirname(__file__), "..", "uploads", "simulations"
    )
    return os.path.join(base, simulation_id, "csi")


def _build_source_map(sources_index: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build source_id → source metadata dict from sources_index."""
    result: Dict[str, Dict[str, Any]] = {}
    for src in sources_index.get("sources", []):
        sid = src.get("source_id")
        if sid:
            result[sid] = src
    return result


def _build_evidence_list(
    source_ids: List[str],
    source_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert source_ids to rich evidence entries."""
    seen: set = set()
    evidence = []
    for sid in source_ids or []:
        if sid in seen:
            continue
        seen.add(sid)
        src = source_map.get(sid, {})
        url = src.get("url") or src.get("metadata", {}).get("url", "")
        if not url:
            continue
        tier = _classify_source_tier(url)
        pmid = _extract_pmid(url)
        evidence.append({
            "source_id": sid,
            "title": src.get("title", url),
            "url": url,
            "tier": tier,
            "label": _source_label(url),
            "pmid": pmid,
            "summary": (src.get("summary") or "")[:300],
        })
    # Sort: tier1 first, then tier2, then tier3
    tier_order = {"tier1": 0, "tier2": 1, "tier3": 2}
    evidence.sort(key=lambda e: tier_order.get(e["tier"], 3))
    return evidence


def _safe_text(value: Any) -> str:
    """Normalize text field — may be str or list of strings from LLM."""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value) if value else ""


def _build_specialist_assessments(
    claims: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
    source_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build per-agent specialist assessment sections."""
    # Index claims by agent_id
    agent_claims: Dict[int, List[Dict[str, Any]]] = {}
    claim_by_id: Dict[str, Dict[str, Any]] = {}
    for claim in claims:
        aid = claim.get("agent_id")
        cid = claim.get("claim_id")
        if aid is not None:
            agent_claims.setdefault(aid, []).append(claim)
        if cid:
            claim_by_id[cid] = claim

    # Index reviews: claim_id → list of reviews
    reviews_on_claim: Dict[str, List[Dict[str, Any]]] = {}
    for review in reviews:
        cid = review.get("claim_id")
        if cid:
            reviews_on_claim.setdefault(cid, []).append(review)

    # Build per-agent profile
    agents_seen: Dict[int, Dict[str, Any]] = {}
    for claim in claims:
        aid = claim.get("agent_id")
        if aid is not None and aid not in agents_seen:
            agents_seen[aid] = {
                "agent_id": aid,
                "agent_name": claim.get("agent_name", f"Agent {aid}"),
                "agent_role": claim.get("role", "specialist"),
                "specialty": claim.get("entity_type", "Medical Specialist"),
            }

    specialists: List[Dict[str, Any]] = []

    for aid, profile in agents_seen.items():
        role = profile["agent_role"]
        agent_claim_list = agent_claims.get(aid, [])

        # Sort claims: final revisions only (latest revision for each chain)
        # Group by revision chain
        chains: Dict[str, Dict[str, Any]] = {}
        for c in agent_claim_list:
            root = c.get("revision_of") or c.get("claim_id")
            existing = chains.get(root)
            if not existing or c.get("round_num", 0) >= existing.get("round_num", 0):
                chains[root] = c
        final_claims = sorted(chains.values(), key=lambda c: c.get("round_num", 0))

        # Build contribution entries
        contributions = []
        all_source_ids: List[str] = []
        for c in final_claims:
            src_ids = c.get("source_ids") or []
            all_source_ids.extend(src_ids)
            contributions.append({
                "claim_id": c.get("claim_id"),
                "claim_text": _safe_text(c.get("text")),
                "confidence": c.get("confidence", 0.0),
                "round_num": c.get("round_num", 0),
                "status": c.get("status", "proposed"),
                "revised": c.get("revision_of") is not None,
                "evidence": _build_evidence_list(src_ids, source_map),
            })

        # Reviews received on this agent's claims
        reviews_received = []
        for c in agent_claim_list:
            cid = c.get("claim_id")
            for rev in reviews_on_claim.get(cid, []):
                if rev.get("agent_id") != aid:  # exclude self-reviews
                    reviews_received.append({
                        "reviewer": rev.get("agent_name", "Unknown"),
                        "reviewer_role": rev.get("role", ""),
                        "verdict": rev.get("verdict", ""),
                        "review_text": _safe_text(rev.get("text")),
                        "confidence": rev.get("confidence", 0.0),
                        "round_num": rev.get("round_num", 0),
                        "claim_text": _safe_text(c.get("text"))[:200],
                    })

        # Reviews conducted by this agent (on other agents' claims)
        reviews_conducted = []
        for rev in reviews:
            if rev.get("agent_id") == aid:
                target_claim = claim_by_id.get(rev.get("claim_id", ""), {})
                author_aid = target_claim.get("agent_id")
                if author_aid != aid:  # skip self-reviews
                    reviews_conducted.append({
                        "claim_author": target_claim.get("agent_name", "Unknown"),
                        "claim_author_role": target_claim.get("role", ""),
                        "claim_text": _safe_text(target_claim.get("text"))[:200],
                        "verdict": rev.get("verdict", ""),
                        "review_text": _safe_text(rev.get("text")),
                        "round_num": rev.get("round_num", 0),
                    })

        # Unique evidence across all contributions
        unique_sources = _build_evidence_list(list(dict.fromkeys(all_source_ids)), source_map)

        specialists.append({
            "agent_id": aid,
            "agent_name": profile["agent_name"],
            "agent_role": role,
            "specialty": profile["specialty"],
            "clinical_relevance_rank": CLINICAL_RELEVANCE_ORDER.get(role, 50),
            "contributions": contributions,
            "reviews_received": reviews_received,
            "reviews_conducted": reviews_conducted,
            "evidence_summary": unique_sources,
            "total_claims": len(final_claims),
            "total_reviews_received": len(reviews_received),
            "total_reviews_conducted": len(reviews_conducted),
        })

    specialists.sort(key=lambda s: s["clinical_relevance_rank"])
    return specialists


def _build_bibliography(source_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build full bibliography from all sources, deduped, sorted by tier."""
    seen_urls: set = set()
    refs: List[Dict[str, Any]] = []
    idx = 1
    tier_order = {"tier1": 0, "tier2": 1, "tier3": 2}
    sorted_sources = sorted(
        source_map.values(),
        key=lambda s: tier_order.get(
            _classify_source_tier(s.get("url") or ""), 3
        )
    )
    for src in sorted_sources:
        url = src.get("url") or ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        origin = src.get("origin", "")
        # Skip project_requirement / project_text placeholders
        if origin in ("project_requirement", "project_text"):
            continue
        pmid = _extract_pmid(url)
        refs.append({
            "ref_num": idx,
            "title": src.get("title", url),
            "url": url,
            "tier": _classify_source_tier(url),
            "label": _source_label(url),
            "pmid": pmid,
            "origin": origin,
        })
        idx += 1
    return refs


def generate_health_report(simulation_id: str) -> Dict[str, Any]:
    """
    Main entry point. Reads all CSI artifacts for simulation_id and builds
    a comprehensive structured medical report with per-agent sections.
    """
    csi_path = _csi_dir(simulation_id)

    claims = _read_jsonl(os.path.join(csi_path, "claims.jsonl"))
    reviews = _read_jsonl(os.path.join(csi_path, "reviews.jsonl"))
    actions = _read_jsonl(os.path.join(csi_path, "agent_actions.jsonl"))
    sources_index = _load_json(os.path.join(csi_path, "sources_index.json"))
    state = _load_json(os.path.join(csi_path, "state.json"))

    if not claims:
        return {"status": "in_progress"}

    source_map = _build_source_map(sources_index)

    # Extract case query from project_requirement source
    case_query = ""
    for src in sources_index.get("sources", []):
        if src.get("origin") == "project_requirement":
            case_query = src.get("content") or src.get("title") or ""
            break

    # Synthesized claims = final output
    synthesized = [c for c in claims if c.get("status") == "synthesized"]
    final_claims = [c for c in claims if c.get("status") in ("proposed", "revised")]

    # Try to extract structured JSON from synthesized claim
    differential_diagnoses = []
    management_plan = []
    safety_alerts = []
    clinical_reasoning = ""

    def _try_parse_synthesis(content: str) -> Optional[Dict[str, Any]]:
        """Parse synthesis JSON — handles truncation by finding last valid boundary."""
        # Strip code-fence markers
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', content.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)
        match = re.search(r'\{', cleaned)
        if not match:
            return None
        blob = cleaned[match.start():]
        # Try raw first
        try:
            return json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            pass
        # Repair strategy: scan backwards from end to find last `}` that closes
        # a complete differential_diagnoses entry, then close the outer structure
        blob = re.sub(r',\s*([}\]])', r'\1', blob)  # remove trailing commas
        # Find all positions of `}` scanning backwards; try each as truncation point
        last_brace_positions = [i for i, ch in enumerate(blob) if ch == '}']
        for pos in reversed(last_brace_positions):
            candidate = blob[:pos + 1]
            # Count unclosed brackets/braces
            opens_bracket = candidate.count('[') - candidate.count(']')
            opens_brace = candidate.count('{') - candidate.count('}')
            suffix = ']' * max(opens_bracket, 0) + '}' * max(opens_brace, 0)
            try:
                result = json.loads(candidate + suffix)
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    # Parse ALL synthesis claims — merge best available fields (each may be truncated at diff points)
    parsed_synths: List[Dict[str, Any]] = []
    for synth in synthesized:
        content = synth.get("text", "")
        parsed = _try_parse_synthesis(content)
        if parsed and isinstance(parsed, dict):
            parsed_synths.append(parsed)

    if parsed_synths:
        # For each field, pick from the parsed synth that has most/best data
        def _best(key: str, default: Any = None) -> Any:
            """Return value from the synth with most data for this key."""
            candidates = [p[key] for p in parsed_synths if key in p and p[key]]
            if not candidates:
                return default
            if isinstance(candidates[0], list):
                return max(candidates, key=len)
            return candidates[0]

        differential_diagnoses = _best("differential_diagnoses", [])
        management_plan = _best("management_plan", [])
        safety_alerts_raw = _best("safety_alerts", [])
        safety_alerts = [str(a) for a in safety_alerts_raw if a]
        clinical_reasoning = _best("clinical_reasoning") or _best("case_summary", "")
    else:
        # Fallback: use raw text of longest synthesis
        if synthesized:
            clinical_reasoning = max(synthesized, key=lambda c: len(c.get("text", ""))).get("text", "")

    # Build per-agent specialist assessments
    specialist_assessments = _build_specialist_assessments(
        claims, reviews, source_map
    )

    # Summary stats
    total_claims = len([c for c in claims if c.get("status") != "synthesized"])
    total_reviews = len(reviews)
    total_rounds = state.get("round_count", 0) or state.get("current_round", 0)
    agents_count = len(specialist_assessments)

    # Build bibliography
    bibliography = _build_bibliography(source_map)

    # Aggregate safety alerts from agent reviews (flag safety-related reviews)
    if not safety_alerts:
        safety_keywords = [
            "contraindicated", "safety", "risk", "hyperkalemia",
            "volume depletion", "hypotension", "genital", "ketoacidosis",
            "renal failure", "overdose", "drug interaction",
        ]
        for rev in reviews:
            txt = _safe_text(rev.get("text")).lower()
            if any(kw in txt for kw in safety_keywords) and rev.get("verdict") == "needs_revision":
                alert = _safe_text(rev.get("text"))[:300]
                if alert and alert not in safety_alerts:
                    safety_alerts.append(alert)

    # Recommended investigations derived from diagnostic claims
    recommended_investigations = []
    investigation_keywords = {
        "echocardiography": "Transthoracic echocardiography (TTE) — assess LVEF, diastolic function, PASP",
        "nt-probnp": "NT-proBNP or BNP measurement — biomarker confirmation of HF",
        "spirometry": "Spirometry + DLCO — exclude pulmonary etiology",
        "eGFR": "Renal function panel (eGFR, creatinine, electrolytes)",
        "egfr": "Renal function panel (eGFR, creatinine, electrolytes)",
        "ecg": "12-lead ECG — baseline cardiac assessment",
        "chest radiograph": "Chest radiograph — assess pulmonary congestion",
        "hba1c": "HbA1c — glycemic control assessment",
        "troponin": "Troponin — rule out ACS",
        "cbc": "CBC — rule out anemia",
    }
    seen_inv: set = set()
    for c in final_claims:
        txt = _safe_text(c.get("text")).lower()
        for kw, label in investigation_keywords.items():
            if kw in txt and label not in seen_inv:
                seen_inv.add(label)
                recommended_investigations.append(label)

    return {
        "status": "completed",
        "simulation_id": simulation_id,
        "case_query": case_query,
        "summary_stats": {
            "agents_count": agents_count,
            "total_claims": total_claims,
            "total_reviews": total_reviews,
            "total_rounds": total_rounds,
            "sources_count": len(bibliography),
            "tier1_sources": len([r for r in bibliography if r["tier"] == "tier1"]),
            "tier2_sources": len([r for r in bibliography if r["tier"] == "tier2"]),
        },
        "differential_diagnoses": differential_diagnoses,
        "clinical_reasoning": clinical_reasoning,
        "recommended_investigations": recommended_investigations,
        "management_plan": management_plan,
        "safety_alerts": safety_alerts,
        "specialist_assessments": specialist_assessments,
        "bibliography": bibliography,
        "disclaimer": (
            "⚠️ This AI-generated assessment is for informational and educational purposes only. "
            "It does not constitute medical advice, diagnosis, or treatment. "
            "Always consult a qualified healthcare provider for medical decisions. "
            "All cited sources should be independently verified."
        ),
    }
