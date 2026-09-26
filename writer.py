"""Optional OpenAI wording pass with strict fallback to the grounded composer."""

from __future__ import annotations

import json
import os
import re
from urllib import request, error


def has_model():
    return bool(os.getenv("OPENAI_API_KEY"))


def improve(message: dict, category: dict, merchant: dict, trigger: dict,
            customer: dict | None = None) -> dict:
    """Only improve an existing eligible message; never use the model to decide eligibility."""
    if not has_model():
        return message
    baseline = message["body"]
    context = {
        "category": {"slug": category.get("slug"), "voice": category.get("voice"),
                     "digest": [d for d in category.get("digest", [])
                                if d.get("id") in {trigger.get("payload", {}).get(k)
                                                    for k in ("top_item_id", "digest_item_id", "alert_id")} ]},
        "merchant": {"identity": merchant.get("identity"), "performance": merchant.get("performance"),
                     "offers": merchant.get("offers"), "signals": merchant.get("signals")},
        "trigger": trigger,
        "customer": ({"identity": customer.get("identity"), "relationship": customer.get("relationship"),
                      "preferences": customer.get("preferences") } if customer else None),
        "baseline": baseline,
    }
    rules = ("Rewrite BASELINE into one concise WhatsApp message for the recipient. "
             "Use only verifiable facts explicitly in BASELINE or CONTEXT. No invented prices, dates, "
             "appointments, statistics, sources, offers, results, competitor names, URLs, or actions completed. "
             "Keep one clear CTA and the same YES/STOP options if present. Match category voice and recipient language. "
             "Avoid marketing hype and medical treatment claims. Do not quote an expired offer. "
             "Return JSON with only body and rationale. Make body useful and specific.")
    endpoint = os.getenv("VERA_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    data = json.dumps({"model": os.getenv("VERA_LLM_MODEL", "gpt-4.1-mini"),
                       "temperature": 0, "max_tokens": 300,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "system", "content": rules},
                                    {"role": "user", "content": "CONTEXT:\n" + json.dumps(context, ensure_ascii=False)}]},
                      ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint + "/chat/completions", data=data,
                          headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                                   "Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=2.5) as response:
            raw = json.load(response)
        candidate = json.loads(raw["choices"][0]["message"]["content"])
        body = candidate.get("body", "").strip()
        if not valid(body, baseline, context):
            return message
        return {**message, "body": body, "rationale": message["rationale"] + " Wording refined with a grounded AI pass."}
    except (TimeoutError, ValueError, KeyError, IndexError, TypeError, error.URLError, OSError):
        return message


def valid(body: str, baseline: str, context: dict) -> bool:
    if len(body) < 25 or len(body) > 550 or body.count("?") > 1:
        return False
    if "YES" in baseline and "yes" not in body.casefold():
        return False
    if "STOP" in baseline and "stop" not in body.casefold():
        return False
    if re.search(r"\b(guaranteed|already (published|sent|booked)|i (published|sent|booked))\b", body, re.I):
        return False
    baseline_numbers = set(re.findall(r"\d+(?:[.,]\d+)*(?:%|km)?", json.dumps(context, ensure_ascii=False)))
    for number in re.findall(r"\d+(?:[.,]\d+)*(?:%|km)?", body):
        if number not in baseline_numbers:
            return False
    if re.search(r"https?://", body) and not re.search(r"https?://", json.dumps(context)):
        return False
    identity = context["customer"]["identity"] if context["customer"] else context["merchant"]["identity"]
    recipient = identity.get("name", "")
    merchant_name = context["merchant"]["identity"].get("name", "")
    if recipient and recipient.casefold().split()[0] not in body.casefold() and merchant_name.casefold() not in body.casefold():
        return False
    return True
