"""Read-only, synthetic scenario preview for the public demo page."""

from __future__ import annotations

import json
from pathlib import Path
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from engine import compose, draft_reply
from writer import has_model, improve


router = APIRouter(prefix="/demo")
DATA = Path(__file__).with_name("dataset")
MERCHANTS = {m["merchant_id"]: m for m in json.loads((DATA / "merchants_seed.json").read_text())["merchants"]}
CUSTOMERS = {c["customer_id"]: c for c in json.loads((DATA / "customers_seed.json").read_text())["customers"]}
TRIGGERS = {t["id"]: t for t in json.loads((DATA / "triggers_seed.json").read_text())["triggers"]}
CATEGORIES = {p.stem: json.loads(p.read_text()) for p in (DATA / "categories").glob("*.json")}
DEMO_IDS = [
    "trg_001_research_digest_dentists",
    "trg_004_perf_dip_bharat",
    "trg_003_recall_due_priya",
    "trg_008_curious_ask_studio11",
    "trg_010_ipl_match_delhi",
    "trg_013_corporate_thali_planning",
    "trg_014_seasonal_acquisition_dip_powerhouse",
    "trg_016_kids_yoga_program_drafting",
    "trg_018_supply_atorvastatin_recall",
    "trg_019_chronic_refill_grandfather",
]
DEMO_IDS = [x for x in DEMO_IDS if x in TRIGGERS]
RATE = {}


class Preview(BaseModel):
    trigger_id: str
    reply: str = ""
    ai: bool = False


@router.get("/scenarios")
def scenarios():
    result = []
    for trigger_id in DEMO_IDS:
        trigger = TRIGGERS[trigger_id]
        merchant = MERCHANTS[trigger["merchant_id"]]
        result.append({"id": trigger_id, "kind": trigger["kind"],
                       "category": merchant["category_slug"],
                       "merchant": merchant["identity"]["name"],
                       "locality": merchant["identity"].get("locality", ""),
                       "scope": trigger["scope"]})
    return {"scenarios": result, "ai_available": has_model()}


@router.post("/preview")
def preview(body: Preview, request: Request):
    if body.trigger_id not in DEMO_IDS:
        raise HTTPException(404, "Unknown synthetic scenario")
    trigger = TRIGGERS[body.trigger_id]
    merchant = MERCHANTS[trigger["merchant_id"]]
    category = CATEGORIES[merchant["category_slug"]]
    customer = CUSTOMERS.get(trigger.get("customer_id"))
    message = compose(category, merchant, trigger, customer)
    if not message:
        return {"decision": "skip", "reason": "Insufficient event facts or matching customer consent.",
                "context": _context(merchant, trigger, customer), "ai_used": False}
    ai_used = False
    if body.ai and has_model():
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        RATE[client] = [t for t in RATE.get(client, []) if now - t < 3600]
        if len(RATE[client]) >= 8:
            raise HTTPException(429, "Demo AI preview limit reached; use the standard preview")
        RATE[client].append(now)
        improved = improve(message, category, merchant, trigger, customer)
        ai_used = improved["body"] != message["body"]
        message = improved
    response = {"decision": "send", "message": {k: v for k, v in message.items() if k != "draft_type"},
                "context": _context(merchant, trigger, customer), "ai_used": ai_used}
    if body.reply.strip():
        text = body.reply.strip().lower()
        if "stop" in text or "not interested" in text:
            response["followup"] = {"action": "end", "text": "Vera stops this conversation."}
        elif any(word in text for word in ("yes", "sure", "draft", "go ahead", "let's do it")):
            response["followup"] = {"action": "send",
                                    "text": draft_reply(merchant, category, trigger, customer)}
        else:
            response["followup"] = {"action": "wait", "text": "Vera pauses until the intent is clear."}
    return response


def _context(merchant, trigger, customer):
    evidence = trigger.get("payload", {})
    return {"business": merchant["identity"]["name"],
            "locality": merchant["identity"].get("locality", ""),
            "event": trigger["kind"].replace("_", " "),
            "facts": [{"name": key.replace("_", " "), "value": value}
                      for key, value in evidence.items() if value is not None][:5],
            "customer": customer["identity"].get("name") if customer else None}
