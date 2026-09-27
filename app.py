"""HTTP interface for the Vera challenge bot. Run with uvicorn app:app."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import re
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine import compose, draft_reply
from writer import has_model, improve
from demo import router as demo_router
from judge_eval import start_if_configured, current_report
from storage import connect, backend
from pathlib import Path


START = time.time()
LOCK = threading.RLock()
app = FastAPI(title="Vera Merchant Assistant", version="0.1.0")
WEB = Path(__file__).with_name("web")
app.mount("/assets", StaticFiles(directory=WEB), name="assets")
app.include_router(demo_router)


with connect() as db:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS contexts (
            scope TEXT NOT NULL, context_id TEXT NOT NULL, version INTEGER NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY (scope, context_id));
        CREATE TABLE IF NOT EXISTS sent (
            recipient TEXT NOT NULL, suppression_key TEXT NOT NULL,
            conversation_id TEXT NOT NULL, sent_at TEXT NOT NULL,
            PRIMARY KEY (recipient, suppression_key));
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY, merchant_id TEXT NOT NULL,
            customer_id TEXT, trigger_id TEXT, last_body TEXT,
            last_turn INTEGER DEFAULT 0, last_inbound TEXT, last_response TEXT,
            auto_count INTEGER DEFAULT 0, status TEXT DEFAULT 'active');
        CREATE TABLE IF NOT EXISTS opt_out (recipient TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS auto_replies (
            merchant_id TEXT NOT NULL, normalized_message TEXT NOT NULL,
            occurrences INTEGER DEFAULT 0, PRIMARY KEY (merchant_id, normalized_message));
        CREATE TABLE IF NOT EXISTS compositions (
            input_hash TEXT PRIMARY KEY, body TEXT NOT NULL, rationale TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS eval_runs (
            run_id TEXT PRIMARY KEY, status TEXT NOT NULL,
            result TEXT NOT NULL, started_at TEXT NOT NULL);
    """)


@app.on_event("startup")
def start_bounded_evaluation():
    start_if_configured()


@app.get("/demo/evaluation", include_in_schema=False)
def evaluation_report():
    return current_report()


def load(db, scope, context_id):
    row = db.execute("SELECT payload FROM contexts WHERE scope=? AND context_id=?",
                     (scope, context_id)).fetchone()
    return json.loads(row["payload"]) if row else None


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (AttributeError, ValueError):
        raise HTTPException(400, "Invalid ISO timestamp")


class ContextPush(BaseModel):
    scope: str
    context_id: str
    version: int = Field(ge=1)
    payload: dict
    delivered_at: str | None = None


class Tick(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class Reply(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str
    message: str
    received_at: str | None = None
    turn_number: int = 1


@app.get("/", include_in_schema=False)
def website():
    return FileResponse(WEB / "index.html")


@app.get("/v1/healthz")
def healthz():
    with LOCK, connect() as db:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for row in db.execute("SELECT scope, count(*) AS n FROM contexts GROUP BY scope"):
            counts[row["scope"]] = row["n"]
        return {"status": "ok", "uptime_seconds": int(time.time() - START),
                "contexts_loaded": counts, "storage_backend": backend()}


@app.get("/v1/metadata")
def metadata():
    return {"team_name": os.getenv("VERA_TEAM_NAME", "Hisham Vera"),
            "team_members": [os.getenv("VERA_MEMBER_NAME", "Hisham Siddiqui")],
            "model": os.getenv("VERA_LLM_MODEL", "gpt-4.1-mini") if has_model() else "deterministic fallback",
            "approach": "grounded trigger selection, drafted follow-ups, consent and dedup checks",
            "contact_email": os.getenv("VERA_CONTACT_EMAIL", ""),
            "version": "0.1.0", "submitted_at": os.getenv("VERA_SUBMITTED_AT", "")}


@app.post("/v1/context")
def context(body: ContextPush):
    if body.scope not in {"category", "merchant", "customer", "trigger"}:
        return JSONResponse({"accepted": False, "reason": "invalid_scope"}, status_code=400)
    if not body.context_id or not isinstance(body.payload, dict):
        return JSONResponse({"accepted": False, "reason": "invalid_payload"}, status_code=400)
    id_field = {"category": "slug", "merchant": "merchant_id", "customer": "customer_id", "trigger": "id"}[body.scope]
    if body.payload.get(id_field) != body.context_id:
        return JSONResponse({"accepted": False, "reason": "context_id_mismatch"}, status_code=400)
    with LOCK, connect() as db:
        row = db.execute("SELECT version FROM contexts WHERE scope=? AND context_id=?",
                         (body.scope, body.context_id)).fetchone()
        if row and row["version"] > body.version:
            return JSONResponse({"accepted": False, "reason": "stale_version",
                                 "current_version": row["version"]}, status_code=409)
        if not row or row["version"] < body.version:
            db.execute("INSERT INTO contexts(scope,context_id,version,payload) VALUES(?,?,?,?) "
                       "ON CONFLICT(scope,context_id) DO UPDATE SET version=excluded.version, payload=excluded.payload",
                       (body.scope, body.context_id, body.version,
                        json.dumps(body.payload, ensure_ascii=False)))
        return {"accepted": True, "ack_id": f"ack_{body.context_id}_v{body.version}",
                "stored_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


def eligible_action(db, trigger_id, now):
    trigger = load(db, "trigger", trigger_id)
    if not trigger or trigger.get("id") != trigger_id:
        return None
    expiry = trigger.get("expires_at")
    if expiry and parse_time(expiry) < now:
        return None
    merchant_id = trigger.get("merchant_id") or trigger.get("payload", {}).get("merchant_id")
    merchant = load(db, "merchant", merchant_id)
    if not merchant:
        return None
    category = load(db, "category", merchant.get("category_slug"))
    if not category:
        return None
    customer_id = trigger.get("customer_id")
    if trigger.get("scope") == "customer" and not customer_id:
        return None
    customer = load(db, "customer", customer_id) if customer_id else None
    if trigger.get("scope") == "customer" and not customer:
        return None
    recipient = customer_id or merchant_id
    if db.execute("SELECT 1 FROM opt_out WHERE recipient=?", (recipient,)).fetchone():
        return None
    message = compose(category, merchant, trigger, customer, now=now)
    if not message:
        return None
    suppression = message["suppression_key"]
    if db.execute("SELECT 1 FROM sent WHERE recipient=? AND suppression_key=?",
                  (recipient, suppression)).fetchone():
        return None
    for row in db.execute("SELECT sent_at FROM sent WHERE recipient=? ORDER BY sent_at DESC LIMIT 4",
                          (recipient,)):
        last = parse_time(row["sent_at"])
        if timedelta(0) <= now - last < timedelta(hours=1):
            return None
    urgency = min(max(int(trigger.get("urgency", 1)), 1), 5)
    specificity = min(len(trigger.get("payload", {})), 5)
    return (urgency * 10 + specificity, recipient, merchant_id, customer_id, trigger, message)


def enhanced(db, message, merchant_id, customer_id, trigger):
    merchant = load(db, "merchant", merchant_id)
    category = load(db, "category", merchant["category_slug"])
    customer = load(db, "customer", customer_id) if customer_id else None
    inputs = [message["body"], category, merchant, trigger, customer]
    cache_key = hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    row = db.execute("SELECT body,rationale FROM compositions WHERE input_hash=?", (cache_key,)).fetchone()
    if row:
        return {**message, "body": row["body"], "rationale": row["rationale"]}
    result = improve(message, category, merchant, trigger, customer)
    db.execute("INSERT OR IGNORE INTO compositions(input_hash,body,rationale) VALUES(?,?,?)",
               (cache_key, result["body"], result["rationale"]))
    return result


@app.post("/v1/tick")
def tick(body: Tick):
    now = parse_time(body.now)
    with LOCK, connect() as db:
        proposals = []
        for trigger_id in dict.fromkeys(body.available_triggers):
            proposed = eligible_action(db, trigger_id, now)
            if proposed:
                proposals.append(proposed)
        proposals.sort(key=lambda row: (-row[0], row[4]["id"]))
        actions = []
        recipients = set()
        ai_calls = 0
        for _, recipient, merchant_id, customer_id, trigger, message in proposals:
            if recipient in recipients or len(actions) >= 20:
                continue
            recipients.add(recipient)
            if has_model() and ai_calls < 2:
                message = enhanced(db, message, merchant_id, customer_id, trigger)
                ai_calls += 1
            conv_id = "conv_" + uuid.uuid4().hex
            action = {"conversation_id": conv_id, "merchant_id": merchant_id,
                      "customer_id": customer_id, "send_as": message["send_as"],
                      "trigger_id": trigger["id"],
                      "template_name": "vera_signal_v1" if not customer_id else "merchant_reminder_v1",
                      "template_params": [message["body"]], "body": message["body"],
                      "cta": message["cta"], "suppression_key": message["suppression_key"],
                      "rationale": message["rationale"]}
            db.execute("INSERT INTO sent(recipient,suppression_key,conversation_id,sent_at) VALUES(?,?,?,?)",
                       (recipient, message["suppression_key"], conv_id, now.isoformat()))
            db.execute("INSERT INTO conversations(conversation_id,merchant_id,customer_id,trigger_id,last_body) "
                       "VALUES(?,?,?,?,?)", (conv_id, merchant_id, customer_id,
                                               trigger["id"], message["body"]))
            actions.append(action)
        return {"actions": actions}


AUTO_TEXT = re.compile(r"thank you for contacting|our team will (respond|reply)|automated assistant|out of office|we have received your (message|query)", re.I)
STOP_TEXT = re.compile(r"\b(stop|unsubscribe|opt\s*out|do not message|don't message|no more messages)\b", re.I)
NO_TEXT = re.compile(r"\b(not interested|no thanks|leave me alone|useless spam)\b", re.I)
YES_TEXT = re.compile(r"\b(yes|yeah|sure|go ahead|let'?s do it|okay do it|ok lets do it|send me|draft it|please do|what'?s next|confirm)\b", re.I)
LATER_TEXT = re.compile(r"\b(later|busy|tomorrow|next week)\b", re.I)


@app.post("/v1/reply")
def reply(body: Reply):
    incoming = body.message.strip()
    if not incoming:
        return {"action": "end", "rationale": "Empty message; avoid a blind follow-up."}
    with LOCK, connect() as db:
        row = db.execute("SELECT * FROM conversations WHERE conversation_id=?",
                         (body.conversation_id,)).fetchone()
        if row and row["last_turn"] == body.turn_number and row["last_inbound"] == incoming:
            return json.loads(row["last_response"])
        if row and row["status"] == "ended":
            return {"action": "end", "rationale": "This conversation was already closed."}
        merchant_id = row["merchant_id"] if row else body.merchant_id
        customer_id = row["customer_id"] if row else body.customer_id
        recipient = customer_id or merchant_id
        merchant = load(db, "merchant", merchant_id) if merchant_id else None
        category = load(db, "category", merchant.get("category_slug")) if merchant else None
        customer = load(db, "customer", customer_id) if customer_id else None
        trigger = load(db, "trigger", row["trigger_id"]) if row and row["trigger_id"] else None
        previous_body = row["last_body"] if row else ""
        normalized = re.sub(r"\s+", " ", incoming.casefold())

        if STOP_TEXT.search(incoming):
            if recipient:
                db.execute("INSERT OR IGNORE INTO opt_out(recipient) VALUES(?)", (recipient,))
            answer = {"action": "end", "rationale": "Explicit stop request recorded."}
        elif NO_TEXT.search(incoming):
            if recipient:
                db.execute("INSERT OR IGNORE INTO opt_out(recipient) VALUES(?)", (recipient,))
            answer = {"action": "end", "rationale": "Merchant/customer declined; end without another pitch."}
        elif AUTO_TEXT.search(incoming) or (row and row["last_inbound"] == incoming):
            prior = db.execute("SELECT occurrences FROM auto_replies WHERE merchant_id=? AND normalized_message=?",
                               (merchant_id or "unknown", normalized)).fetchone()
            count = (prior["occurrences"] if prior else 0) + 1
            db.execute("INSERT INTO auto_replies(merchant_id,normalized_message,occurrences) VALUES(?,?,?) "
                       "ON CONFLICT(merchant_id,normalized_message) DO UPDATE SET occurrences=excluded.occurrences",
                       (merchant_id or "unknown", normalized, count))
            answer = ({"action": "end", "rationale": "Repeated business auto-reply; stop the conversation."}
                      if count >= 2 else
                      {"action": "wait", "wait_seconds": 1800,
                       "rationale": "Likely WhatsApp Business auto-reply; allow a human time to respond."})
        elif LATER_TEXT.search(incoming):
            answer = {"action": "wait", "wait_seconds": 1800,
                      "rationale": "Recipient requested time; pause."}
        elif re.search(r"\b(file my gst|gst return|tax filing)\b", incoming, re.I):
            answer = {"action": "send", "body": "I can help with your business messages and drafts here. For GST filing, please check with your accountant.",
                      "cta": "none", "rationale": "Answer off-topic request honestly without claiming tax expertise."}
        elif YES_TEXT.search(incoming):
            draft = draft_reply(merchant or {}, category or {}, trigger or {}, customer)
            answer = {"action": "send", "body": draft, "cta": "none",
                      "rationale": "Recipient accepted; supplied a reviewable draft or concrete next step without claiming to have published it."}
        elif "?" in incoming or re.search(r"\b(how|why|what|price|cost|details|abstract)\b", incoming, re.I):
            draft = draft_reply(merchant or {}, category or {}, trigger or {}, customer)
            answer = {"action": "send", "body": draft, "cta": "none",
                      "rationale": "Replied to the question with available context, leaving unsupported details for human confirmation."}
        else:
            answer = {"action": "wait", "wait_seconds": 1800,
                      "rationale": "Unclear reply; pause instead of repeating or guessing."}

        if answer.get("action") == "send" and (answer["body"] == previous_body or (row and row["last_turn"] >= 5)):
            answer = {"action": "end", "rationale": "Conversation limit or repeated response reached."}
        if row:
            db.execute("UPDATE conversations SET last_turn=?,last_inbound=?,last_response=?,status=?,last_body=? "
                       "WHERE conversation_id=?",
                       (body.turn_number, incoming, json.dumps(answer, ensure_ascii=False),
                        "ended" if answer["action"] == "end" else "active",
                        answer.get("body", previous_body), body.conversation_id))
        return answer
