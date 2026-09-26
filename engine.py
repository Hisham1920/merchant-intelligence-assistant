"""Grounded message and reply decisions for the magicpin challenge."""

from __future__ import annotations

from datetime import datetime
import re


def fact(value):
    return str(value).strip() if value is not None else ""


def short_name(merchant):
    identity = merchant.get("identity") or {}
    return identity.get("owner_first_name") or identity.get("name", "there")


def active_offer(merchant):
    return next((o.get("title") for o in merchant.get("offers", [])
                 if o.get("status") == "active" and o.get("title")), None)


def digest_item(category, item_id):
    return next((item for item in category.get("digest", [])
                 if item.get("id") == item_id), None)


def percent(value):
    try:
        return f"{abs(float(value)) * 100:g}%"
    except (TypeError, ValueError):
        return ""


def date_label(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d %b")
    except ValueError:
        return fact(value)


def consent_allows(customer, kind):
    if not customer or customer.get("preferences", {}).get("channel", "whatsapp") != "whatsapp":
        return False
    consent = customer.get("consent") or {}
    scopes = set(consent.get("scope") or [])
    if not consent.get("opted_in_at") or not scopes:
        return False
    allowed = {
        "recall_due": {"recall_reminders"},
        "appointment_tomorrow": {"appointment_reminders"},
        "trial_followup": {"program_updates", "appointment_reminders"},
        "chronic_refill_due": {"refill_reminders"},
        "wedding_package_followup": {"bridal_package_followup"},
        "customer_lapsed_soft": {"winback_offers", "promotional_offers"},
        "customer_lapsed_hard": {"winback_offers", "promotional_offers"},
    }.get(kind, set())
    return bool(scopes & allowed) and customer.get("preferences", {}).get("reminder_opt_in", True)


def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict | None:
    """Return a grounded message, or None when the supplied facts cannot support one."""
    kind = trigger.get("kind", "")
    payload = trigger.get("payload") or {}
    if payload.get("placeholder"):
        return None
    name = short_name(merchant)
    business = merchant.get("identity", {}).get("name", "your business")
    if business.startswith(f"Dr. {name}"):
        name = f"Dr. {name}"
    offer = active_offer(merchant)
    locality = merchant.get("identity", {}).get("locality", "")
    scope = trigger.get("scope", "merchant")
    hook = ""
    ask = ""
    cta = "binary"
    draft_type = ""

    if scope == "customer":
        if not customer or customer.get("merchant_id") != merchant.get("merchant_id"):
            return None
        if not consent_allows(customer, kind):
            return None
        who = customer.get("identity", {}).get("name", "there")
        hello = f"Hi {who}, {business} here. "
        if kind == "recall_due":
            due = date_label(payload.get("due_date"))
            if not due:
                return None
            hook = f"Your follow-up for {fact(payload.get('service_due', 'your last visit')).replace('_', ' ')} is due around {due}."
            ask = "Would you like us to help arrange a visit? Reply YES, or STOP for no reminders."
        elif kind == "appointment_tomorrow":
            slot = payload.get("appointment_iso") or payload.get("appointment_at")
            if not slot:
                return None
            hook = f"A visit is scheduled for {date_label(slot)}."
            ask = "Can you make it? Reply YES to confirm or STOP to stop reminders."
        elif kind == "trial_followup":
            day = date_label(payload.get("trial_date"))
            if not day:
                return None
            hook = f"Following up after your trial on {day}."
            ask = "Would you like details of the next session? Reply YES or STOP."
        elif kind == "chronic_refill_due":
            day = date_label(payload.get("stock_runs_out_iso"))
            if not day:
                return None
            hook = f"A refill reminder is due around {day}."
            ask = "Would you like the pharmacy to help with your usual refill? Reply YES or STOP."
        elif kind == "wedding_package_followup":
            day = date_label(payload.get("wedding_date"))
            if not day:
                return None
            hook = f"Checking in after your bridal trial ahead of {day}."
            ask = "Want a draft prep plan to review? Reply YES or STOP."
            draft_type = "bridal prep plan"
        elif kind in {"customer_lapsed_soft", "customer_lapsed_hard"}:
            days = payload.get("days_since_last_visit")
            if days is None:
                return None
            hook = f"It has been {days} days since your last visit."
            focus = payload.get("previous_focus") or customer.get("preferences", {}).get("training_focus")
            if merchant.get("category_slug") == "gyms" and focus:
                hook += f" You previously focused on {fact(focus).replace('_', ' ')}."
                ask = "Want us to suggest a suitable session after checking availability? Reply YES, or STOP to stop messages."
            else:
                ask = "Would you like to hear about a suitable next visit? Reply YES or STOP."
        else:
            return None
        if customer.get("identity", {}).get("language_pref") in {"hi", "hi-en mix"}:
            ask = "Aap interested hain toh YES reply karein; reminders band karne ke liye STOP."
        body = hello + hook + " " + ask
        return _message(body, cta, "merchant_on_behalf", trigger, kind, draft_type)

    if kind in {"research_digest", "regulation_change", "cde_opportunity", "supply_alert"}:
        item_id = (payload.get("top_item_id") or payload.get("digest_item_id")
                   or payload.get("alert_id"))
        item = digest_item(category, item_id)
        if not item:
            return None
        source = item.get("source")
        hook = f"{item.get('title', 'A new item')}" + (f" ({source})." if source else ".")
        if kind == "regulation_change":
            hook += f" Deadline: {date_label(payload.get('deadline_iso'))}." if payload.get("deadline_iso") else ""
            ask = "Want a short checklist of what to review? Reply YES."
            draft_type = "review checklist"
        elif kind == "supply_alert":
            batches = payload.get("affected_batches") or []
            hook += f" Listed batches: {', '.join(map(str, batches))}." if batches else ""
            ask = "Want a stock-check checklist drafted? Reply YES."
            draft_type = "stock check checklist"
        elif kind == "cde_opportunity" and item.get("date"):
            credits = payload.get("credits") or item.get("credits")
            detail = f" {credits} CDE credits." if credits else ""
            fee = item.get("actionable", "")
            hook = f"{item.get('title')} ({item.get('source', 'source not listed')}) is on {date_label(item['date'])}.{detail}"
            if fee:
                hook += f" {fee.rstrip('.')}."
            ask = "Want a brief summary of the practical takeaways for your clinic? Reply YES."
            draft_type = "webinar summary"
        else:
            ask = "Want a short, shareable summary drafted? Reply YES."
            draft_type = "shareable summary"
    elif kind in {"perf_dip", "seasonal_perf_dip", "perf_spike"}:
        metric, change = payload.get("metric"), percent(payload.get("delta_pct"))
        if not metric or not change:
            return None
        direction = "down" if float(payload["delta_pct"]) < 0 else "up"
        hook = f"Your {metric} are {direction} {change} over {payload.get('window', 'the latest period')}."
        if kind == "seasonal_perf_dip" and payload.get("is_expected_seasonal"):
            hook += " This may be seasonal; it is worth checking before changing your offer."
        ask = "Want me to draft one focused Google post using your current offer? Reply YES." if offer else "Want me to draft one focused Google post for review? Reply YES."
        draft_type = "Google post"
    elif kind == "review_theme_emerged":
        theme, count = payload.get("theme"), payload.get("occurrences_30d")
        if not theme or count is None:
            return None
        hook = f"{count} reviews mentioned {fact(theme).replace('_', ' ')} in the last 30 days."
        ask = "Want me to draft a practical reply and one action to address it? Reply YES."
        draft_type = "review reply"
    elif kind == "competitor_opened":
        competitor, distance = payload.get("competitor_name"), payload.get("distance_km")
        if not competitor or distance is None:
            return None
        hook = f"{competitor} opened {distance} km from {business}{f' in {locality}' if locality else ''}."
        if payload.get("their_offer"):
            hook += f" Their listed offer is {fact(payload['their_offer'])}."
        if offer:
            hook += f" Your current offer is {offer}."
        ask = "Want a draft that explains what makes your service useful without a price war? Reply YES."
        draft_type = "offer comparison"
    elif kind == "festival_upcoming":
        festival, day = payload.get("festival"), date_label(payload.get("date"))
        if not festival or not day or payload.get("days_until", 0) > 45:
            return None
        hook = f"{festival} is on {day}."
        ask = "Want me to draft a relevant post for your business? Reply YES."
        draft_type = "festival post"
    elif kind == "ipl_match_today":
        if not payload.get("match") or not payload.get("match_time_iso"):
            return None
        hook = f"{payload['match']} is scheduled at {payload.get('venue', 'the stadium')} on {date_label(payload['match_time_iso'])}."
        ask = "Want a match-day post drafted with details you approve? Reply YES."
        draft_type = "match-day post"
    elif kind == "milestone_reached":
        value, goal = payload.get("value_now"), payload.get("milestone_value")
        if value is None or goal is None:
            return None
        metric = payload.get("metric", "reviews").replace("_", " ")
        hook = f"You are at {value} {metric}, {max(0, goal - value)} away from {goal}."
        ask = "Want a review-request draft for recent customers? Reply YES."
        draft_type = "review request"
    elif kind == "renewal_due":
        days = payload.get("days_remaining")
        if days is None:
            return None
        hook = f"Your {payload.get('plan', 'subscription')} plan has {days} days remaining."
        ask = "Want a concise summary of your renewal details? Reply YES."
        draft_type = "renewal summary"
    elif kind == "gbp_unverified":
        if payload.get("verified") is not False:
            return None
        hook = "Your Google Business Profile is marked unverified."
        ask = "Want the verification steps listed for review? Reply YES."
        draft_type = "verification steps"
    elif kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message")
        if days is None:
            return None
        hook = f"It's been {days} days since we last discussed {fact(payload.get('last_topic', 'your profile')).replace('_', ' ')}."
        calls_delta = (merchant.get("performance", {}).get("delta_7d") or {}).get("calls_pct")
        if isinstance(calls_delta, (int, float)) and calls_delta < 0:
            hook += f" Your calls also fell {percent(calls_delta)} over the last 7 days."
        ask = "Would a fresh draft for your Google listing help? Reply YES."
        draft_type = "Google post"
    elif kind == "curious_ask_due":
        if not payload.get("ask_template"):
            return None
        calls_delta = (merchant.get("performance", {}).get("delta_7d") or {}).get("calls_pct")
        if isinstance(calls_delta, (int, float)) and calls_delta > 0:
            hook = f"Calls to {business} rose {percent(calls_delta)} in the last 7 days. Which service are customers asking for most this week?"
        else:
            hook = f"Quick question about {business}: what service are customers asking for most this week?"
        ask = "Tell me one and I'll draft a Google post for that demand."
        cta = "open_ended"
        draft_type = "Google post"
    elif kind == "active_planning_intent":
        topic = payload.get("intent_topic", "").replace("_", " ")
        if not topic or not payload.get("merchant_last_message"):
            return None
        if merchant.get("category_slug") == "restaurants" and "thali" in topic:
            hook = ("For your corporate thali idea, a first draft could list menu choices, "
                    "group size, delivery area and time, then a price you confirm. "
                    f"We can position it for offices near {locality}." if locality else
                    "For your corporate thali idea, a first draft could list menu choices, group size, delivery time and a price you confirm.")
        elif merchant.get("category_slug") == "gyms" and "kids yoga" in topic:
            hook = ("For your kids yoga program, let's outline age group, session times, "
                    "instructor, guardian contact and a fee you approve before advertising it.")
        else:
            hook = f"For your {topic} idea, let's outline the audience, service details, timing and a price you approve."
        ask = "Want customer-ready copy drafted from that outline? Reply YES."
        draft_type = "customer-ready copy"
    elif kind == "category_seasonal":
        trends = payload.get("trends") or []
        if not trends:
            return None
        topics = [re.sub(r"_demand_[+-]?\d+", "", fact(trend)).replace("_", " ") for trend in trends[:3]]
        hook = f"Your seasonal category update flags demand changes for {', '.join(topics)}."
        ask = "Want a shelf-check draft for these items, using only stock your team confirms? Reply YES."
        draft_type = "seasonal checklist"
    elif kind == "winback_eligible":
        days = payload.get("days_since_expiry")
        if days is None:
            return None
        hook = f"Your plan expired {days} days ago."
        ask = "Want a summary of your account changes since then? Reply YES."
        draft_type = "account summary"
    else:
        return None

    if not hook:
        return None
    prefix = f"{name}, " if name else ""
    if offer and kind in {"perf_dip", "perf_spike", "festival_upcoming"}:
        hook += f" Your active offer is {offer}."
    body = f"{prefix}{hook} {ask}"
    return _message(body, cta, "vera", trigger, kind, draft_type)


def _message(body, cta, send_as, trigger, kind, draft_type):
    return {
        "body": re.sub(r"\s+", " ", body).strip(),
        "cta": cta,
        "send_as": send_as,
        "suppression_key": trigger.get("suppression_key") or trigger.get("id", ""),
        "rationale": f"Used the supplied {kind} event and matching business context; offered a {draft_type or 'clear next step'} without claiming work was completed.",
        "draft_type": draft_type,
    }


def draft_reply(merchant: dict, category: dict, trigger: dict, customer: dict | None = None):
    """Produce an honest preview of work the bot can complete without external integrations."""
    kind = trigger.get("kind", "")
    payload = trigger.get("payload") or {}
    business = merchant.get("identity", {}).get("name", "your business")
    offer = active_offer(merchant)
    if kind in {"research_digest", "regulation_change", "cde_opportunity", "supply_alert"}:
        item = digest_item(category, payload.get("top_item_id") or payload.get("digest_item_id") or payload.get("alert_id"))
        if item:
            return f"Draft summary for your review: {item.get('title', '')}. {item.get('summary', '')} Source supplied: {item.get('source', 'not listed')}. I can edit this before you share it."
    if kind == "review_theme_emerged":
        theme = fact(payload.get("theme", "the issue")).replace("_", " ")
        return f"Draft reply for {business}: 'Thank you for flagging the {theme}. We will review what happened and follow up with your team directly.' Please check the wording before posting."
    if kind == "active_planning_intent":
        topic = fact(payload.get("intent_topic", "your idea")).replace("_", " ")
        if merchant.get("category_slug") == "restaurants" and "thali" in topic:
            return (f"Corporate thali copy for {business}, for your review: 'Planning an office meal? "
                    "Tell us your group size, preferred menu, delivery area and time. We will confirm "
                    "the dishes, availability and quote before you order.' Add the actual menu and price after your team approves them.")
        if merchant.get("category_slug") == "gyms" and "kids yoga" in topic:
            return (f"Kids yoga program copy for {business}, for your review: 'Interested in yoga for your child? "
                    "Ask us about the age group, instructor and session schedule. Our team will confirm "
                    "suitability, places and fees before registration.' Please approve the age range, staff and times before sharing.")
        return f"Starter draft for {business}: '{business} is exploring a {topic}. Tell us what you need and we will confirm the details and price with you.' I have left pricing and availability open for your approval."
    if kind == "competitor_opened":
        service = {"dentists": "dental visit", "salons": "salon appointment", "gyms": "fitness session",
                   "restaurants": "meal", "pharmacies": "pharmacy help"}.get(merchant.get("category_slug"), "service")
        return (f"Draft for {business}: 'Looking for a {service}? Our current offer is "
                f"{offer or 'available on request'}. Ask us what it includes and whether it suits you.' "
                "Please check the service details before posting; this draft does not assume anything about another business.")
    if kind == "category_seasonal":
        items = [re.sub(r"_demand_[+-]?\d+", "", fact(s)).replace("_", " ")
                 for s in (payload.get("trends") or [])[:3]]
        return (f"Shelf-check draft for {business}: confirm current stock, pack sizes and prices for "
                f"{', '.join(items)}; place available items where customers can find them; "
                "ask a pharmacist to review any health advice before sharing a seasonal post. No stock has been checked yet.")
    if kind in {"perf_dip", "perf_spike", "festival_upcoming", "dormant_with_vera", "curious_ask_due"}:
        place = merchant.get("identity", {}).get("locality")
        detail = f"{offer}." if offer else "Ask us about services and current availability."
        location = f" in {place}" if place else ""
        return f"Google post draft for your review: '{business}{location} — {detail} Message us for details.' This is a draft; it has not been published."
    if customer:
        return f"I can help {business} with this request. A team member must confirm any appointment, delivery, or price before it is booked."
    return f"Draft for {business}: 'We are ready to help with {offer or 'your next visit'}. Message us for current details.' Please review before posting; I have not published or sent anything."
