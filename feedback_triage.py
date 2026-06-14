"""Canonical three-card feedback triage backend — copy into MeniscusMaximus / CodeMonkeys."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel


class ProposalRerollRequest(BaseModel):
    id: str
    slot: Any  # int 0-2 or "all"


class ProposalUpdateRequest(BaseModel):
    id: str
    slot: int
    text: str = ""


class ProposalAcceptRequest(BaseModel):
    id: str
    solution: str
    acceptedSlot: Optional[int] = None
    reviewNote: str = ""
    note: str = ""
    status: str = "planned"


class FeedbackActionRequest(BaseModel):
    id: str
    status: str


ARCHIVED_STATUSES = frozenset({"fixed", "dismissed", "done", "declined"})


def _valid_feedback_id(rid: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{16}", (rid or "").strip()))


def heuristic_proposals(report: dict) -> list[str]:
    cat = report.get("category") or "bug"
    msg = (report.get("message") or "")[:200]
    cat_label = {"bug": "bug", "improvement": "improvement", "question": "question"}.get(cat, cat)
    return [
        f"[FIX] Recommended: address this {cat_label} — {msg} Ship the smallest safe change that resolves the report, then mark fixed.",
        f"[INVESTIGATE] Reproduce locally with the attached context/screenshot, confirm scope, then either fix or split into a smaller follow-up.",
        f"[DISMISS] Close as won't-fix / already handled / insufficient detail — leave a short note for future triage.",
    ]


def ensure_proposals(
    report: dict,
    meta: dict,
    *,
    llm_fn: Optional[Callable[[str], Optional[str]]] = None,
    reroll_slot: Any = None,
) -> dict:
    proposals = list(meta.get("proposals") or ["", "", ""])
    while len(proposals) < 3:
        proposals.append("")
    fresh = None
    if llm_fn:
        prompt = (
            "Return exactly 3 short triage actions as a JSON array of strings for this user feedback report. "
            "Each must start with [FIX], [INVESTIGATE], or [DISMISS]. Option 0 is recommended.\n\n"
            f"Category: {report.get('category')}\nMessage: {report.get('message')}\nContext: {report.get('context')}"
        )
        try:
            raw = llm_fn(prompt)
            if raw:
                text = raw.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```$", "", text)
                parsed = json.loads(text)
                if isinstance(parsed, list) and len(parsed) >= 3:
                    fresh = [str(p) for p in parsed[:3]]
        except Exception:
            fresh = None
    if not fresh:
        fresh = heuristic_proposals(report)
    if reroll_slot == "all":
        meta["proposals"] = fresh
        meta["recommendedSlot"] = 0
    elif isinstance(reroll_slot, int) and 0 <= reroll_slot <= 2:
        proposals[reroll_slot] = fresh[reroll_slot]
        meta["proposals"] = proposals
    elif not any(p.strip() for p in proposals):
        meta["proposals"] = fresh
        meta["recommendedSlot"] = 0
    else:
        meta["proposals"] = proposals
    if "recommendedSlot" not in meta:
        meta["recommendedSlot"] = 0
    return meta


def merge_report_with_meta(report: dict, meta: dict | None) -> dict:
    out = dict(report)
    meta = meta or {}
    out["status"] = meta.get("status", out.get("status", "new"))
    out["reviewNote"] = meta.get("reviewNote") or meta.get("note", "")
    out["proposals"] = meta.get("proposals") or ["", "", ""]
    out["recommendedSlot"] = meta.get("recommendedSlot", 0)
    out["chosenSolution"] = meta.get("chosenSolution", "")
    out["acceptedSlot"] = meta.get("acceptedSlot")
    return out


def register_feedback_triage_routes(
    app,
    *,
    verify_owner,
    load_statuses: Callable[[], dict],
    save_statuses: Callable[[dict], None],
    find_report: Callable[[str], dict | None],
    valid_statuses: set[str],
    llm_fn: Optional[Callable[[str], Optional[str]]] = None,
    accept_status: str = "planned",
    archive_statuses: frozenset[str] | None = None,
):
    archive = archive_statuses or ARCHIVED_STATUSES

    def _meta_for(rid: str) -> dict:
        statuses = load_statuses()
        meta = statuses.get(rid) or {"status": "new"}
        report = find_report(rid)
        if report:
            meta = ensure_proposals(report, meta, llm_fn=llm_fn)
            statuses[rid] = meta
            save_statuses(statuses)
        return meta

    def _item(rid: str) -> dict:
        report = find_report(rid)
        if not report:
            raise HTTPException(status_code=404, detail="not found")
        statuses = load_statuses()
        meta = statuses.get(rid) or {"status": "new"}
        meta = ensure_proposals(report, meta, llm_fn=llm_fn)
        statuses[rid] = meta
        save_statuses(statuses)
        return merge_report_with_meta(report, meta)

    @app.post("/api/feedback/proposals/reroll")
    def reroll(req: ProposalRerollRequest, user: str = Depends(verify_owner)):
        rid = (req.id or "").strip()
        if not _valid_feedback_id(rid):
            raise HTTPException(status_code=400, detail="Invalid id.")
        report = find_report(rid)
        if not report:
            raise HTTPException(status_code=404, detail="not found")
        statuses = load_statuses()
        meta = statuses.get(rid) or {"status": "new"}
        slot = req.slot
        if slot != "all":
            slot = int(slot)
        meta = ensure_proposals(report, meta, llm_fn=llm_fn, reroll_slot=slot)
        statuses[rid] = meta
        save_statuses(statuses)
        return {"item": merge_report_with_meta(report, meta)}

    @app.post("/api/feedback/proposals/update")
    def update(req: ProposalUpdateRequest, user: str = Depends(verify_owner)):
        rid = (req.id or "").strip()
        if not _valid_feedback_id(rid):
            raise HTTPException(status_code=400, detail="Invalid id.")
        if req.slot < 0 or req.slot > 2:
            raise HTTPException(status_code=400, detail="Invalid slot.")
        report = find_report(rid)
        if not report:
            raise HTTPException(status_code=404, detail="not found")
        statuses = load_statuses()
        meta = statuses.get(rid) or {"status": "new"}
        proposals = list(meta.get("proposals") or ["", "", ""])
        while len(proposals) < 3:
            proposals.append("")
        proposals[req.slot] = (req.text or "")[:4000]
        meta["proposals"] = proposals
        statuses[rid] = meta
        save_statuses(statuses)
        return {"item": merge_report_with_meta(report, meta)}

    @app.post("/api/feedback/proposals/accept")
    def accept(req: ProposalAcceptRequest, user: str = Depends(verify_owner)):
        rid = (req.id or "").strip()
        if not _valid_feedback_id(rid):
            raise HTTPException(status_code=400, detail="Invalid id.")
        solution = (req.solution or "").strip()
        if not solution:
            raise HTTPException(status_code=400, detail="solution required")
        report = find_report(rid)
        if not report:
            raise HTTPException(status_code=404, detail="not found")
        statuses = load_statuses()
        meta = statuses.get(rid) or {"status": "new"}
        meta["chosenSolution"] = solution[:4000]
        meta["acceptedSlot"] = req.acceptedSlot
        meta["reviewNote"] = (req.reviewNote or req.note or "")[:1000]
        meta["status"] = accept_status if (req.status or accept_status) in valid_statuses else accept_status
        meta["accepted_ts"] = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())
        statuses[rid] = meta
        save_statuses(statuses)
        return {"item": merge_report_with_meta(report, meta)}

    @app.post("/api/feedback/action")
    def action(req: FeedbackActionRequest, user: str = Depends(verify_owner)):
        rid = (req.id or "").strip()
        status = (req.status or "").strip().lower()
        if not _valid_feedback_id(rid):
            raise HTTPException(status_code=400, detail="Invalid id.")
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail="Invalid status.")
        report = find_report(rid)
        if not report:
            raise HTTPException(status_code=404, detail="not found")
        statuses = load_statuses()
        meta = statuses.get(rid) or {"status": "new"}
        meta["status"] = status
        if status in archive:
            meta["resolved_ts"] = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())
        statuses[rid] = meta
        save_statuses(statuses)
        return {"item": merge_report_with_meta(report, meta)}

    return _item, _meta_for
