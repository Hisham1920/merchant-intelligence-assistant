"""Grounded message and reply decisions for the magicpin challenge."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def plain_window(value):
    label = fact(value)
    return f"{label[:-1]} days" if re.fullmatch(r"\d+d", label) else label or "the latest period"


def category_label(merchant):
    if merchant.get("category_slug") == "gyms" and "yoga" in merchant.get("identity", {}).get("name", "").lower():
        return "yoga studio"
    return {"dentists": "clinic", "salons": "salon", "restaurants": "restaurant",
            "gyms": "gym", "pharmacies": "pharmacy"}.get(merchant.get("category_slug"), "business")


def trend_topics(trends):
    """Read the direction in a supplied trend token without guessing its units."""
    rising, falling = [], []
    for trend in trends[:4]:
        match = re.fullmatch(r"(.+)_demand_([+-])\d+", fact(trend))
        if match:
            (rising if match.group(2) == "+" else falling).append(match.group(1).replace("_", " "))
    return rising, falling


def recall_slot(payload, now=None):
    """Mention a supplied appointment option only while it remains in the future."""
    try:
        due = datetime.fromisoformat(payload["due_date"].replace("Z", "+00:00"))
        for option in payload.get("available_slots") or []:
            slot = datetime.fromisoformat(option["iso"].replace("Z", "+00:00"))
            current = now or datetime.now(timezone.utc)
            if slot.tzinfo and due.tzinfo is None:
                due = due.replace(tzinfo=slot.tzinfo)
            if slot.tzinfo and current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            if current < slot and abs(slot - due) <= timedelta(days=14):
                return slot.strftime("%d %b at %I:%M %p").replace(" at 0", " at ")
    except (KeyError, TypeError, ValueError):
        return ""
    return ""


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


def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None,
            now: datetime | None = None) -> dict | None:
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
            service = re.sub(r"(\d+)_month", r"\1-month", fact(payload.get("service_due", "your last visit"))).replace("_", " ")
            hook = f"Your follow-up for {service} is due around {due}."
            slot = recall_slot(payload, now)
            if slot:
                hook += f" We have {slot} listed as an option; we can check whether it is still open."
            ask = "Would you like the clinic to check a suitable visit near then? Reply YES, or STOP for no reminders."
        elif kind == "appointment_tomorrow":
            slot = payload.get("appointment_iso") or payload.get("appointment_at")
            if not slot:
                return None
            try:
                parsed = datetime.fromisoformat(slot.replace("Z", "+00:00"))
                time_label = parsed.strftime("%d %b at %I:%M %p").replace(" at 0", " at ")
            except ValueError:
                time_label = date_label(slot)
            hook = f"A visit is scheduled for {time_label}."
            ask = "Can you make it? Reply YES to confirm or STOP to stop reminders."
        elif kind == "trial_followup":
            day = date_label(payload.get("trial_date"))
            if not day:
                return None
            hook = f"Following up after your trial at {business} on {day}."
            ask = "Would you like details of the next session? Reply YES or STOP."
        elif kind == "chronic_refill_due":
            day = date_label(payload.get("stock_runs_out_iso"))
            if not day:
                return None
            hook = f"Your refill reminder is due around {day}."
            ask = "Would you like the pharmacy to help with your usual refill? Reply YES or STOP."
        elif kind == "wedding_package_followup":
            day = date_label(payload.get("wedding_date"))
            if not day:
                return None
            hook = f"Checking in after your bridal trial ahead of your {day} wedding."
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
                preferred = fact(customer.get("preferences", {}).get("preferred_slots", "")).replace("_", " ")
                ask = (f"Want us to check {preferred} options to ease back in? Reply YES, or STOP to stop messages."
                       if preferred else "Want us to suggest a suitable session after checking availability? Reply YES, or STOP to stop messages.")
            else:
                ask = "Would you like to hear about a suitable next visit? Reply YES or STOP."
        else:
            return None
        if customer.get("identity", {}).get("language_pref") in {"hi", "hi-en mix"}:
            ask = "Time check karna ho toh YES reply karein; reminders band karne ke liye STOP." if kind == "recall_due" else "Aap chahen toh YES reply karein; messages band karne ke liye STOP."
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
        if kind == "research_digest":
            if item.get("patient_segment") == "high_risk_adults" and "high_risk_adult_cohort" in merchant.get("signals", []):
                hook += " This may be relevant to the high-risk adults you see; check the study before changing recall intervals."
            ask = "Want a concise evidence summary for your practice? Reply YES."
            draft_type = "evidence summary"
        elif kind == "regulation_change":
            hook += f" Deadline: {date_label(payload.get('deadline_iso'))}." if payload.get("deadline_iso") else ""
            ask = "Want a short checklist for reviewing your own X-ray equipment against the supplied guidance? Reply YES." if merchant.get("category_slug") == "dentists" else "Want a short checklist for reviewing what applies to your business? Reply YES."
            draft_type = "review checklist"
        elif kind == "supply_alert":
            batches = payload.get("affected_batches") or []
            hook += f" Listed batches: {', '.join(map(str, batches))}." if batches else ""
            ask = "Want a batch-check draft for your pharmacy team? Reply YES."
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
        hook = f"Your {fact(metric).replace('_', ' ')} are {direction} {change} over {plain_window(payload.get('window'))}."
        if kind == "perf_dip" and merchant.get("category_slug") == "dentists" and locality:
            hook = f"Calls to your {locality} dental practice are down {change} over {plain_window(payload.get('window'))}." if metric == "calls" else hook
            if "unverified_gbp" in merchant.get("signals", []):
                hook += " Your Google listing is also marked unverified."
        if kind == "seasonal_perf_dip" and payload.get("is_expected_seasonal"):
            hook += " This may be seasonal; it is worth checking before changing your offer."
        driver = fact(payload.get("likely_driver", "")).replace("_", " ")
        if kind == "perf_spike" and driver:
            hook += f" The supplied event points to your {driver} as a possible driver."
        if offer and kind == "perf_spike":
            ask = f"Want a {category_label(merchant)} post draft for {locality or business} using your current offer? Reply YES."
        elif merchant.get("category_slug") == "dentists":
            ask = "Want a short listing checklist and patient-friendly post draft for your clinic? Reply YES." if "unverified_gbp" in merchant.get("signals", []) else "Want a patient-friendly post draft for your clinic to review? Reply YES."
        else:
            ask = "Want one focused Google post draft that you can review before sharing? Reply YES."
        draft_type = "Google post"
    elif kind == "review_theme_emerged":
        theme, count = payload.get("theme"), payload.get("occurrences_30d")
        if not theme or count is None:
            return None
        hook = f"{count} reviews mentioned {fact(theme).replace('_', ' ')} in the last 30 days."
        ask = f"Want a reply draft for {business} and one action for your team to consider? Reply YES."
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
        ask = "Want a patient-friendly draft highlighting your own cleaning offer? Reply YES." if merchant.get("category_slug") == "dentists" and offer and "cleaning" in offer.lower() else "Want a draft about your own service without a price war? Reply YES."
        draft_type = "offer comparison"
    elif kind == "festival_upcoming":
        festival, day = payload.get("festival"), date_label(payload.get("date"))
        if not festival or not day or payload.get("days_until", 0) > 45:
            return None
        hook = f"{festival} is on {day}."
        ask = f"Want a {category_label(merchant)} post for {locality} drafted for review? Reply YES." if locality else "Want a relevant post for your business drafted for review? Reply YES."
        draft_type = "festival post"
    elif kind == "ipl_match_today":
        if not payload.get("match") or not payload.get("match_time_iso"):
            return None
        try:
            match_time = datetime.fromisoformat(payload["match_time_iso"].replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        start_time = match_time.strftime("%I:%M %p").lstrip("0")
        hook = f"{payload['match']} is scheduled at {payload.get('venue', 'the stadium')} on {date_label(payload['match_time_iso'])} at {start_time}."
        if merchant.get("category_slug") == "restaurants" and "pizza" in business.lower():
            ask = f"Want a match-night pizza post for {business}{' in ' + locality if locality else ''}, using menu details you confirm? Reply YES."
        else:
            ask = f"Want a match-day post for {business} drafted with details you approve? Reply YES."
        draft_type = "match-day post"
    elif kind == "milestone_reached":
        value, goal = payload.get("value_now"), payload.get("milestone_value")
        if value is None or goal is None:
            return None
        metric = "reviews" if payload.get("metric") == "review_count" else payload.get("metric", "reviews").replace("_", " ")
        hook = f"You are at {value} {metric}, {max(0, goal - value)} away from {goal}."
        ask = f"Want a thank-you and review-request draft for recent {business} customers? Reply YES."
        draft_type = "review request"
    elif kind == "renewal_due":
        days = payload.get("days_remaining")
        if days is None:
            return None
        hook = f"Your {payload.get('plan', 'subscription')} plan has {days} days remaining."
        ask = "Want a concise summary of the plan and deadline for your review? Reply YES."
        draft_type = "renewal summary"
    elif kind == "gbp_unverified":
        if payload.get("verified") is not False:
            return None
        hook = f"The Google Business Profile for {business}{' in ' + locality if locality else ''} is marked unverified."
        path = payload.get("verification_path")
        ask = "Want a short guide to which postcard or phone verification option applies? Reply YES." if path == "postcard_or_phone_call" else "Want the verification steps listed for review? Reply YES."
        draft_type = "verification steps"
    elif kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message")
        if days is None:
            return None
        hook = f"It's been {days} days since we last discussed {fact(payload.get('last_topic', 'your profile')).replace('_', ' ')}."
        calls_delta = (merchant.get("performance", {}).get("delta_7d") or {}).get("calls_pct")
        if isinstance(calls_delta, (int, float)) and calls_delta < 0:
            hook += f" Your calls also fell {percent(calls_delta)} over the last 7 days."
        ask = f"Want a fresh listing post for {business}{' in ' + locality if locality else ''}, using only services you confirm? Reply YES."
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
            if offer and "thali" in offer.lower():
                hook += f" Your listed {offer} can be a reference, while you confirm the separate group price."
        elif merchant.get("category_slug") == "gyms" and "kids yoga" in topic:
            hook = ("For your kids yoga program, let's outline age group, session times, "
                    "instructor, guardian contact and a fee you approve before advertising it."
                    f" We can frame it for families near {locality}." if locality else
                    "For your kids yoga program, let's outline age group, times, instructor and a fee you approve.")
        else:
            hook = f"For your {topic} idea, let's outline the audience, service details, timing and a price you approve."
        ask = "Want customer-ready copy drafted from that outline? Reply YES."
        draft_type = "customer-ready copy"
    elif kind == "category_seasonal":
        trends = payload.get("trends") or []
        if not trends:
            return None
        rising, falling = trend_topics(trends)
        if not rising and not falling:
            return None
        rising = ["cold and cough" if x == "cold cough" else x for x in rising]
        falling = ["cold and cough" if x == "cold cough" else x for x in falling]
        hook = f"Your seasonal update shows demand rising for {', '.join(rising)}" if rising else "Your seasonal update shows changing demand"
        if falling:
            hook += f" and falling for {', '.join(falling)}"
        hook += "."
        ask = f"Want a shelf-check draft for {business}{' in ' + locality if locality else ''}, after your team confirms actual stock? Reply YES."
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
    if offer and kind == "perf_spike":
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


def reply_intent(incoming: str) -> str:
    """Read short English and Hindi-English choices before generating a reply."""
    if re.search(r"\b(stop|unsubscribe|opt\s*out|do not message|don't message|no more messages|band karo|mat bhejo|message band|msg band)\b", incoming, re.I):
        return "stop"
    if re.search(r"\b(not interested|no thanks|leave me alone|useless spam|nahi chahiye|nahin chahiye)\b", incoming, re.I) or re.fullmatch(r"\s*(?:no|nahi|nahin)\s*[.!]?\s*", incoming, re.I):
        return "no"
    if re.search(r"\b(later|busy|tomorrow|next week|baad mein|baad me|kal baat)\b", incoming, re.I):
        return "later"
    if re.search(r"\b(yes|yeah|sure|go ahead|let'?s do it|okay do it|ok lets do it|haan|han|haanji|bilkul|thik hai|theek hai)\b", incoming, re.I):
        return "yes"
    if "?" in incoming or re.search(r"\b(how|why|what|when|where|price|cost|details|abstract|kitna|kitni|kitne|kab|kaise|kya|fees|daam|timing|available)\b", incoming, re.I):
        return "question"
    if re.search(r"\b(send me|draft it|please do|confirm it|kar do|bana do|bhejo|bhej do)\b", incoming, re.I):
        return "yes"
    return "other"


def reply_in_language(text: str, incoming: str, intent: str) -> str:
    """Use a small Hindi-English framing when the recipient used Hindi-English."""
    if re.search(r"\b(haan|han|haanji|bilkul|bhejo|bhej|kitna|kitni|kitne|kab|kaise|kya|daam|batao|thik hai|theek hai)\b", incoming, re.I):
        return ("Bilkul, yeh draft review ke liye hai: " if intent == "yes" else
                "Jo details abhi available hain: ") + text
    return text


def draft_reply(merchant: dict, category: dict, trigger: dict, customer: dict | None = None,
                now: datetime | None = None, reply_text: str = ""):
    """Make the promised draft or concrete next step from the approved event facts."""
    kind = trigger.get("kind", "")
    payload = trigger.get("payload") or {}
    business = merchant.get("identity", {}).get("name", "your business")
    place = merchant.get("identity", {}).get("locality", "")
    location = f" in {place}" if place else ""
    offer = active_offer(merchant)
    item = digest_item(category, payload.get("top_item_id") or payload.get("digest_item_id") or payload.get("alert_id"))
    if kind == "supply_alert" and item:
        batches = payload.get("affected_batches") or []
        codes = ", ".join(map(str, batches)) if batches else "the listed batch numbers"
        return (f"Stock-check draft for {business}: compare stock and invoices against {codes}; "
                f"ask a pharmacist to verify the supplied {item.get('source', 'alert')} before deciding on affected items. "
                "Record matches and contact the distributor if confirmed. Stock has not been checked.")
    if kind == "regulation_change" and item:
        deadline = date_label(payload.get("deadline_iso"))
        return (f"Clinic checklist draft: review your X-ray equipment and film or sensor records against "
                f"the supplied {item.get('source', 'guidance')}; confirm whether it applies to {business}; "
                f"record what needs updating{f' before {deadline}' if deadline else ''}. "
                "Verify the original circular before changing clinical practice.")
    if kind == "cde_opportunity" and item:
        return (f"Webinar brief for {business}: {item.get('title', 'CDE event')} on {date_label(item.get('date'))}; "
                f"{payload.get('credits') or item.get('credits', 'listed')} CDE credits. "
                f"{item.get('actionable', 'Confirm registration details with the organizer')}. "
                "Check the organizer's calendar before registering.")
    if kind == "research_digest" and item:
        return (f"Draft summary for {business}: the supplied {item.get('source', 'digest')} lists "
                f"'{item.get('title', 'this update')}'. {item.get('summary', '')} "
                "Review the original research and patient fit before sharing clinical advice.")
    if kind == "active_planning_intent":
        topic = fact(payload.get("intent_topic", "your idea")).replace("_", " ")
        if merchant.get("category_slug") == "restaurants" and "thali" in topic:
            return (f"Customer copy draft for {business}: 'Planning an office thali meal{location}? "
                    "Tell us your group size, delivery area and preferred time. We will confirm menu, availability "
                    "and a separate bulk quote before you order.' "
                    + ("Your listed weekday lunch price is not a group quote." if offer and "thali" in offer.lower()
                       else "Confirm the group price before sharing."))
        if merchant.get("category_slug") == "gyms" and "kids yoga" in topic:
            return (f"Customer copy draft for {business}: 'Interested in a kids yoga program{location}? "
                    "Ask our team about age suitability, instructor and session times. We will confirm places and fees "
                    "before registration.' The age range, schedule and price still need your approval.")
        return (f"Customer copy draft for {business}: 'We are exploring {topic}. Tell us what you need and "
                "our team will confirm timing, availability and price.' Approve the details before sharing.")
    if kind == "category_seasonal":
        rising, falling = trend_topics(payload.get("trends") or [])
        return (f"Shelf-check draft for {business}: verify actual stock and pack prices for "
                f"{', '.join(rising + falling)}. Give priority to the rising items if available, "
                "and ask a pharmacist to check any health advice. No stock has been checked.")
    if kind == "gbp_unverified":
        path = payload.get("verification_path", "")
        modes = "postcard or phone option, if offered" if path == "postcard_or_phone_call" else "available option"
        return (f"Verification checklist for {business}: open your Google Business Profile, confirm its details, "
                f"check the {modes}, and complete the steps shown there. No verification has been submitted.")
    if kind == "review_theme_emerged":
        theme = fact(payload.get("theme", "the concern")).replace("_", " ")
        count = payload.get("occurrences_30d")
        return (f"Review reply draft for {business}: 'Thank you for pointing out the {theme}. "
                "Please message our team with the details so we can look into your experience.' "
                f"Team action: investigate the {count} recent mentions before making a public promise.")
    if kind == "competitor_opened":
        detail = f" Our currently listed offer is {offer}." if offer else ""
        return (f"Customer post draft for {business}{location}: 'Looking for a {category_label(merchant)}? "
                f"Ask our team which service fits your needs and what it includes.{detail}' "
                "Confirm offer eligibility before sharing; do not make claims about another business.")
    if kind == "ipl_match_today":
        return (f"Match-day post draft: '{payload.get('match', 'The match')} is scheduled on "
                f"{date_label(payload.get('match_time_iso'))}. Planning a pizza night{location}? "
                f"Ask {business} about today's confirmed menu and prices.' "
                "Check opening hours before posting; no promotion has been assumed.")
    if kind == "milestone_reached":
        goal = payload.get("milestone_value")
        return (f"Review-request draft for {business}: 'Thank you for visiting. "
                "If you would like to share an honest review, it helps other customers know what to expect.' "
                f"The profile shows {payload.get('value_now')} reviews; {goal} is the next milestone. "
                "Do not offer rewards for reviews.")
    if kind == "curious_ask_due":
        selected = next((o["title"] for o in merchant.get("offers", [])
                         if o.get("status") == "active" and o.get("title")
                         and re.search(re.escape(reply_text.strip()), o["title"], re.I)), None) if reply_text.strip() and len(reply_text.strip()) <= 35 else None
        if selected:
            return (f"Google post draft for {business}{location}: '{selected}. "
                    "Message our team to confirm current availability and terms.' "
                    "Please review before publishing; this does not claim it is your most requested service.")
        if offer:
            return (f"Google post draft for {business}{location}: '{offer}. "
                    "Ask our team for current details.' This uses an existing listed offer; "
                    "choose the most requested service yourself before publishing.")
    if kind in {"perf_dip", "seasonal_perf_dip", "perf_spike", "dormant_with_vera", "festival_upcoming"}:
        feature = f"{offer}. " if offer and kind == "perf_spike" else ""
        return (f"Google post draft for {business}{location}: '{feature}Ask us about our current "
                f"{category_label(merchant)} services and availability.' "
                "Check the details before publishing; no post has been published.")
    if kind == "renewal_due":
        return (f"Renewal summary draft for {business}: your {payload.get('plan', 'current')} plan shows "
                f"{payload.get('days_remaining')} days remaining. Check the current price, included services "
                "and renewal date in your account before deciding; no renewal was made.")
    if kind == "winback_eligible":
        return (f"Account review for {business}: the supplied record shows the plan expired "
                f"{payload.get('days_since_expiry')} days ago. Check the current status and any changes "
                "in your account before choosing a new plan; no renewal was made.")
    if customer:
        name = customer.get("identity", {}).get("name", "there")
        if kind == "recall_due":
            due = date_label(payload.get("due_date"))
            slot = recall_slot(payload, now)
            option = f" {slot} is listed as an option to verify." if slot else ""
            return (f"Draft reply for {name}: 'Your follow-up at {business} is due around {due}.{option} "
                    "Please ask the clinic to confirm a suitable time.' No appointment has been booked.")
        if kind == "chronic_refill_due":
            return (f"Draft reply for {name}: 'Your refill reminder is around "
                    f"{date_label(payload.get('stock_runs_out_iso'))}. Ask {business} to check your "
                    "prescription, stock and delivery details before confirming.' No medicine was ordered.")
        if kind == "customer_lapsed_hard":
            focus = fact(payload.get("previous_focus", "your earlier goal")).replace("_", " ")
            slot = fact(customer.get("preferences", {}).get("preferred_slots", "")).replace("_", " ")
            return (f"Draft reply for {name}: 'Welcome back to {business}. We can check "
                    f"{slot + ' ' if slot else ''}sessions that suit your {focus} goal. "
                    "The team will confirm availability before any booking.'")
        if kind == "trial_followup":
            return (f"Draft reply for {name}: 'Thanks for trying {business} on "
                    f"{date_label(payload.get('trial_date'))}. Tell us your preferred time and "
                    "the team can check the next session.' No place has been reserved.")
        if kind == "wedding_package_followup":
            return (f"Prep-plan draft for {name}: 'Ahead of {date_label(payload.get('wedding_date'))}, "
                    f"ask {business} to review your trial notes, the service you want, and a suitable schedule.' "
                    "The team must confirm suitability, availability and price.")
        return (f"Draft reply for {name}: '{business} can check a suitable next visit with you." 
                " Please confirm timing and price with the team.' No booking has been made.")
    return (f"Draft for {business}: '{business}{location} can help you with available services. "
            "Message our team for confirmed details.' Review before publishing; nothing has been sent.")


def answer_question(question: str, merchant: dict, category: dict, trigger: dict,
                    customer: dict | None = None, now: datetime | None = None) -> str:
    """Answer a specific question from known facts, or state the missing fact."""
    payload = trigger.get("payload") or {}
    kind = trigger.get("kind", "")
    business = merchant.get("identity", {}).get("name", "the business")
    if re.search(r"\b(price|cost|fee|fees|charge|rate|kitna|kitni|kitne|daam|paisa)\b", question, re.I):
        item = digest_item(category, payload.get("top_item_id") or payload.get("digest_item_id"))
        if kind == "cde_opportunity" and item and item.get("actionable"):
            return f"The supplied event lists: {item['actionable']}. Please confirm the current fee with the organizer."
        if customer:
            return f"I don't have a confirmed price for your visit or refill. Please ask {business} to confirm it before booking or ordering."
        if kind == "active_planning_intent":
            return ("A price for the new plan hasn't been confirmed. "
                    + ("The listed weekday lunch thali price is a separate offer; " if active_offer(merchant) and
                       "thali" in active_offer(merchant).lower() else "") +
                    "please approve a group quote first." if "thali" in payload.get("intent_topic", "") else
                    "A fee for this new program hasn't been approved yet. Please set it before sharing the draft.")
        offer = active_offer(merchant)
        if offer and kind in {"competitor_opened", "perf_spike", "curious_ask_due"}:
            return f"{business} currently lists {offer}. This may not cover the service you mean; confirm eligibility and the final price with the team."
        return f"I don't have a confirmed price for that service. Please verify it with {business} before sharing a quote."
    if re.search(r"\b(when|date|time|timing|slot|available|kab|samay)\b", question, re.I):
        item = digest_item(category, payload.get("digest_item_id") or payload.get("top_item_id"))
        if kind == "recall_due":
            option = recall_slot(payload, now)
            return (f"The follow-up is due around {date_label(payload.get('due_date'))}. "
                    + (f"{option} is listed as an option; ask {business} to confirm it." if option else
                       f"I don't have a current open slot; ask {business} to confirm one."))
        if kind == "cde_opportunity" and item and item.get("date"):
            return f"The supplied calendar lists {date_label(item['date'])}. Please confirm the exact time with the organizer."
        if kind == "ipl_match_today" and payload.get("match_time_iso"):
            return f"The supplied schedule lists {date_label(payload['match_time_iso'])}; check the event organizer for the latest time."
        return f"I don't have a confirmed time or availability. Please check with {business} before making plans."
    if kind in {"research_digest", "regulation_change", "cde_opportunity", "supply_alert"}:
        item = digest_item(category, payload.get("top_item_id") or payload.get("digest_item_id") or payload.get("alert_id"))
        if item:
            return (f"The supplied {item.get('source', 'category note')} is about {item.get('title', 'this update')}. "
                    "Please verify the original source before changing clinical care or stock handling.")
    if kind == "active_planning_intent":
        return (f"The next step is a draft for {business}; the audience, timing, availability and "
                "price still need your approval. Nothing has been advertised.")
    return (f"I don't have that answer in the supplied details for {business}. "
            "The team should confirm it; I can help draft a message using what we do know.")
