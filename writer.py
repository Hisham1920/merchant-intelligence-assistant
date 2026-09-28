"""Optional OpenAI wording pass with strict fallback to the grounded composer."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from urllib import request, error


def has_model():
    return bool(os.getenv("OPENAI_API_KEY"))


def improve(message: dict, category: dict, merchant: dict, trigger: dict,
            customer: dict | None = None) -> dict:
    """Only improve an existing eligible message; never use the model to decide eligibility."""
    if not has_model():
        return message
    baseline = message["body"]
    item_ids = {trigger.get("payload", {}).get(key) for key in ("top_item_id", "digest_item_id", "alert_id")}
    anchors = [offer["title"] for offer in merchant.get("offers", [])
               if offer.get("status") == "active" and offer.get("title")
               and offer["title"].casefold() in baseline.casefold()]
    for item in category.get("digest", []):
        if item.get("id") in item_ids:
            anchors.extend(item[key] for key in ("title", "source")
                           if item.get(key) and item[key].casefold() in baseline.casefold())
    anchors.extend(value for key in ("competitor_name", "match", "venue")
                   if isinstance(value := trigger.get("payload", {}).get(key), str)
                   and value.casefold() in baseline.casefold())
    context = {
        "category": {"slug": category.get("slug"), "voice": category.get("voice", {}).get("tone")},
        "merchant": {"identity": {"name": merchant.get("identity", {}).get("name", ""),
                                   "owner_first_name": merchant.get("identity", {}).get("owner_first_name", "")}},
        "trigger_kind": trigger.get("kind"),
        "customer": ({"identity": {"name": customer.get("identity", {}).get("name", "")},
                      "language_pref": customer.get("identity", {}).get("language_pref") } if customer else None),
        "fact_anchors": anchors,
        "baseline": baseline,
    }
    rules = ("Rewrite BASELINE into one concise WhatsApp message for the recipient. "
             "Keep factual sentences verbatim, especially any sentence containing an event, status, "
             "metric, date, price or offer. You may polish the greeting and call to action; if no safe "
             "polish is possible, return BASELINE unchanged. The other context is for greeting and tone "
             "only; never add facts from it. "
             "Preserve all numbers, currency amounts and the YES/STOP choices. Match recipient language. "
             "Avoid marketing hype, medical claims, new promises and actions completed. "
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
    if len(re.split(r"(?<=[.!?])\s+", body)) > len(re.split(r"(?<=[.!?])\s+", baseline)):
        return False
    if "YES" in baseline and "yes" not in body.casefold():
        return False
    if "STOP" in baseline and "stop" not in body.casefold():
        return False
    if re.search(r"\b(guaranteed|already (published|sent|booked)|i (published|sent|booked))\b", body, re.I):
        return False
    for claim in (r"\b(caused|causes|fixed|checked|confirmed|completed)\b",
                  r"\bwill (recover|increase|improve|sell out)\b"):
        if re.search(claim, body, re.I) and not re.search(claim, baseline, re.I):
            return False
    if any(re.search(pattern, body, re.I) and not re.search(pattern, baseline, re.I)
           for pattern in (r"\bfree\b", r"\b(best|top-rated|limited time|guaranteed|cure|published|booked)\b")):
        return False
    numeric = re.compile(r"(?<![\w])(?:₹\s*)?\d+(?:[.,]\d+)*(?:\s?%|\s?km)?", re.I)
    def tokens(value):
        return Counter(re.sub(r"\s+", "", match.group()).lower() for match in numeric.finditer(value))
    expected, actual = tokens(baseline), tokens(body)
    if actual - expected or expected - actual:
        return False
    # Keep factual statements attached to their subjects. A bag of equal numbers
    # cannot tell whether two prices or dates were exchanged in a rewrite.
    fact_words = re.compile(
        r"\b(?:verified|unverified|offer|listed|scheduled|effective|due|rose|fell|"
        r"rising|falling|up|down|opened|demand|marked|credits|last visit|points to)\b", re.I)
    normalized_body = " ".join(body.casefold().split())
    for sentence in re.split(r"(?<=[.!?])\s+", baseline):
        sentence = sentence.strip()
        if (numeric.search(sentence) or fact_words.search(sentence)) and " ".join(
            sentence.rstrip(".!?").casefold().split()
        ) not in normalized_body:
            return False
    # These words often reverse the meaning of an otherwise unchanged fact.
    for word in ("verified", "unverified", "available", "unavailable", "confirmed",
                 "expired", "not", "never", "only"):
        if len(re.findall(r"\b" + word + r"\b", body, re.I)) > len(
            re.findall(r"\b" + word + r"\b", baseline, re.I)
        ):
            return False
    if any(anchor.casefold() not in body.casefold() for anchor in context.get("fact_anchors", [])):
        return False
    if re.search(r"https?://", body) and not re.search(r"https?://", baseline):
        return False
    for change in ("up", "down", "rose", "fell", "rising", "falling"):
        if re.search(r"\b" + change + r"\b", body, re.I) and not re.search(r"\b" + change + r"\b", baseline, re.I):
            return False
    identity = context["customer"]["identity"] if context["customer"] else context["merchant"]["identity"]
    recipient = identity.get("name", "") or ""
    merchant_name = context["merchant"]["identity"].get("name", "")
    owner_name = context["merchant"]["identity"].get("owner_first_name", "")
    words = recipient.casefold().split()
    distinctive = words[1] if len(words) > 1 and words[0].rstrip(".") == "dr" else (words[0] if words else "")
    if distinctive and distinctive not in body.casefold() and merchant_name.casefold() not in body.casefold() and (not owner_name or owner_name.casefold() not in body.casefold()):
        return False
    if context["customer"] and distinctive and distinctive not in body.casefold():
        return False
    return True
