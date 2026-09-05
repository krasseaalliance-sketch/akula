from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import HunterRun


def write_hot_leads_report(run: HunterRun, json_path: str | Path, md_path: str | Path) -> None:
    payload: dict[str, Any] = {
        "profile": run.profile_id,
        "status": "UNVERIFIED_UNTIL_MANUAL_REVIEW",
        "summary": {
            "signals_seen": run.signals_seen, "signals_ingested": run.signals_ingested,
            "signals_analyzed": run.signals_analyzed, "rejected": run.rejected,
            "needs_review": run.needs_review, "qualified_hot_demand": run.qualified_hot_demand,
            "potential": run.potential, "hot": run.hot, "very_hot": run.very_hot,
            "opportunity": run.opportunity, "duplicates": run.duplicates,
            "provider_failures": run.provider_failures, "average_latency_ms": run.average_latency_ms,
            "manual_review_count": run.manual_review_count, "rejected_breakdown": run.rejected_breakdown,
            **run.metrics,
        },
        "source_policies": [policy.__dict__ for policy in run.source_policies],
        "leads": [lead.to_dict() for lead in run.leads],
        "top_hot_leads": [lead.to_dict() for lead in run.leads if lead.priority_score >= 70][:10],
    }
    Path(json_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    lines = ["# Lead Hunter — Vitrina Hot Leads", "", "Статус: UNVERIFIED_UNTIL_MANUAL_REVIEW", "", "## Run summary", ""]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## Qualified HOT_DEMAND", ""]
    if not run.leads:
        lines.append("No qualified leads were produced. No artificial TOP-10 was created.")
    for lead in run.leads:
        lines += [
            f"### #{lead.rank} — {lead.result_class} priority={lead.priority_score}/100",
            f"- Intent score: `{lead.intent_score}`; commercial fit: `{lead.commercial_fit_score}`; legacy lead score: `{lead.lead_score}`",
            f"- Intent: `{lead.intent}`; product: `{lead.requested_product}`",
            f"- Location: {lead.location}; budget: {lead.budget}; deadline: {lead.deadline}; urgency: {lead.urgency}",
            f"- Freshness: {lead.freshness}", f"- Source: [{lead.source}]({lead.source_url})",
            f"- Actionable now: `{lead.actionable_now}`; verification: `{lead.verification_status}`; dedupe: `{lead.dedupe_status}`",
            f"- Signal excerpt: {lead.original_signal_excerpt}",
            f"- Why lead: {lead.why_this_is_a_lead}", f"- Why Vitrina: {lead.why_it_fits_vitrina}",
            f"- Score explanation: {lead.score_explanation.human_summary}", "",
        ]
    Path(md_path).write_text("\n".join(lines), encoding="utf-8")
