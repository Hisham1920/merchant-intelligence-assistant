# Vera bot — build log and plain-English technical guide

**Goal:** Submit one public URL for a working merchant assistant. The same Python service must show a usable demo website and answer the five HTTP calls in magicpin's challenge brief.

## Start here, g — the easy version

Imagine Vera as a helper at a small business. Magicpin gives her **fact sheets** about a type of business, one particular shop, an event, and sometimes a customer. Vera decides if it is a good time to message. If it is, she writes a short message. If someone replies YES, she prepares a draft they can check. She does not really send WhatsApp messages, make bookings, or post on Google in this challenge.

| Word we use | In simple language |
| --- | --- |
| **Context** | A fact sheet Magicpin sends us. |
| **Trigger** | The event that could justify a message, like calls falling this week. |
| **Tick** | Magicpin asking: “Given these events, should Vera send anything now?” |
| **API endpoint** | A specific web address where Magicpin sends that question or a reply. |
| **Database** | Vera's notebook for remembering the fact sheets, past messages, and STOP requests. |
| **Draft** | Text the merchant can review; it has not been published. |
| **LLM** | An AI model that can improve writing or act as a practice judge. |

**The five numbers in a judge score** ask: Is the message specific? Does it suit this business type? Does it suit this particular shop? Why is it being sent today? Would someone want to reply? Each gets 0–10. We add them to get a practice score out of 50. A score such as 35/50 is **not** “70% accurate.” We separately count when Vera sends or stays quiet, and we watch for invented facts.

## What we are building

When an event happens, Vera reads four pieces of information: the business category, the particular merchant, the event, and optionally the customer. It decides whether messaging is appropriate. For useful events it writes a message with one clear next step. When the recipient replies, it drafts a useful response or stops.

The website is for us to inspect and demonstrate the bot. The competition judge calls the API directly. The website does not send real WhatsApp messages.

## Decisions made

1. Python and FastAPI serve the website and the judge API from one project.
2. SQLite remembers context versions, sent messages, opt-outs, and conversations during the test.
3. Rules decide whether a message is safe and relevant. An OpenAI model can improve wording; if its call fails or the answer breaks the factual checks, the built-in wording still works.
4. A merchant's YES produces a reviewable draft. Vera never claims it posted on Google, booked an appointment, or sent WhatsApp messages.
5. Customer outreach requires matching consent, and a placeholder event never becomes an invented fact.

## Progress

- [x] Read the challenge ZIP and screenshots; found that the public URL and five endpoints are the main submission route.
- [x] Implemented and locally tested the base API, versioned context storage, trigger decisions, and reply handling.
- [x] Six focused automated checks passed; a live HTTP request produced a merchant message and a follow-up draft.
- [x] Add an interactive website with 10 example scenarios and reply previews.
- [x] Add optional OpenAI wording and grounded output checks; no key is stored in the project.
- [x] Add a Render deployment recipe and verify website routes, all 10 scenarios, and six service tests locally.
- [x] Loaded the expanded challenge set (5 categories, 50 merchants, 200 customers, 100 triggers) and exercised all 30 test pairs locally. Many generated triggers are placeholders, so staying quiet on those is intentional.
- [x] Put the complete project in the private GitHub repository `Hisham1920/magicpin-vera-bot`.
- [x] Improved the generated corporate thali, kids yoga, pharmacy seasonality and nearby competitor messages. Six tests still pass after the update.
- [x] Verified the Render account and deployed the website and API at `https://magicpin-vera-bot-06ct.onrender.com`.
- [x] Tested the live website, a YES follow-up, health, metadata and an empty judge tick. Health showed four zero context counts before judging, as expected.
- [x] Confirmed the key redeployment is Live, metadata reports `gpt-4.1-mini`, and the AI preview refined a grounded performance-dip message. Other previews fell back to built-in wording as designed.
- [x] Submitted the public URL to the competition (confirmed by Hisham). The URL can still be updated.

## Files to know

| File | What it does |
| --- | --- |
| `app.py` | Receives judge requests, remembers conversations, serves demo routes |
| `storage.py` | Chooses local SQLite or durable Render Postgres and adapts database queries |
| `engine.py` | Decides and writes grounded messages and first reply drafts |
| `web/` | Demo webpage files |
| `tests/` | Checks endpoint and messaging behavior, including a process restart |
| `dataset/` | Magicpin's supplied synthetic practice data |
| `render.yaml` | Hosting settings for Render |
| `DEPLOY_RENDER.md` | Exact steps to get the public URL |
| `writer.py` | Optional OpenAI rewrite with safe fallback |

## What the project actually does, step by step

1. The judge sends a **category**, **merchant**, **customer**, or **trigger** JSON document to `POST /v1/context`. Think of a context as a fact sheet. A category describes what is appropriate for dentists, salons, restaurants, gyms, or pharmacies. A merchant sheet holds the particular business's name, figures, offers, and history. A customer sheet holds their relationship and consent. A trigger describes the event that could justify messaging now.
2. `app.py` checks the context ID and version and writes the JSON through `storage.py`: to SQLite on a laptop or Postgres when `DATABASE_URL` is configured on Render. A newer version replaces an older one, while a repeat of the same version is a no-op. This is how the judge can later inject a fresh research item or changed performance numbers.
3. On `POST /v1/tick`, the judge supplies its simulated time and a list of available trigger IDs. `app.py` loads the matching fact sheets. It checks expiry, opt-outs, previous sends, and recent contact before asking `engine.py` to compose a message.
4. `engine.py` checks that the event has enough real facts. It matches customer reminders to the customer's consent scope and channel. It can return **no message**. For a supported event it writes a short WhatsApp-style message and a single next step. A placeholder trigger is skipped rather than turned into a made-up event.
5. Eligible messages are ranked by urgency and specificity. The service sends at most one per recipient per tick and at most 20 actions total. The first two actions on a tick can also be polished by `writer.py` when the key is configured; the others use the built-in text to keep response time bounded.
6. `writer.py` asks `gpt-4.1-mini` to rewrite an already approved message. Its validator checks length, essential reply words, some obvious unsupported numbers/URLs, recipient identity, and claims about completed actions. If the AI call times out or fails validation, the original message is returned. **This validator does not prove every sentence is factual.** The model decides wording, not whether we contact someone.
7. `app.py` returns an action containing its body, recipient IDs, template name, suppression key, explanation, and a unique conversation ID. The judge simulates delivery; this project has no actual WhatsApp or Google publishing integration.
8. If the judge calls `POST /v1/reply`, the service reads the conversation and classifies YES, STOP, no thanks, later, auto-replies, certain questions, and unclear replies. `engine.py` can return a *draft for review*. Repeated auto-replies eventually end the conversation. A STOP records an opt-out. It never asserts that a draft was published or that an appointment was booked.

### Example to make the flow concrete

For Bharat Dental Care, a `perf_dip` trigger says calls dropped 50% over seven days. A tick loads Bharat's merchant sheet and that trigger. The decision rules allow a merchant-facing nudge, then the wording step may refine it. The proposed message mentions the 50% decrease and offers a Google post **draft**. If Bharat replies YES, `/v1/reply` returns copy for Bharat to review. Nothing is posted to Google automatically.

### Which file to open when changing something

| Change you want | Open this file | Locate this part |
| --- | --- | --- |
| Change which events are allowed to send | `engine.py` | `compose()` and its `kind` branches |
| Change customer consent rules | `engine.py` | `consent_allows()` |
| Change the draft given after YES | `engine.py` | `draft_reply()` |
| Change the judge endpoints, saving, dedup, or ranking | `app.py` | `/v1/context`, `eligible_action()`, `/v1/tick`, `/v1/reply` |
| Change the saved-state database | `storage.py` and `render.yaml` | `connect()`, Postgres database definition, `DATABASE_URL` |
| Change AI instructions, model, or safety checks | `writer.py` | `improve()` and `valid()` |
| Change the interactive scenarios and replies | `demo.py` and `web/app.js` | `/demo/scenarios`, `/demo/preview`, `selectScenario()`, `sendReply()` |
| Change site appearance | `web/index.html` and `web/style.css` | Page structure and styles |
| Change deployment settings | `render.yaml` | Start command, environment settings, health check |
| Change synthetic sample facts | `dataset/` | Category files and three seed JSON files |
| Check behavior after changes | `tests/test_service.py` | Six automated service cases |

The **website** reads 10 bundled sample scenarios through `demo.py` and makes a read-only preview. The **judge** uses the five `/v1/*` API endpoints and sends its own data; testing the website alone does not prove the judge run will score highly. `README.md` explains the project, `RUN_ME_FIRST.md` gives Windows commands, and `DEPLOY_RENDER.md` explains deployment.

## What we measured on 26 September 2026

**Official score or accuracy: unknown.** The challenge's judge grades each message on specificity, category fit, merchant fit, trigger relevance, and engagement (0–10 each; maximum 50), then considers new context, conversations, and operational penalties. No official scorecard or labeled reference answer has been provided. There is no justified percentage for message quality or hallucination frequency yet.

**Service tests at the first submission:** `python3 -m unittest discover -s tests -v` passed **6/6**. These cover context versions, a grounded send, repeat suppression, a new digest item, customer consent and expiry, YES and STOP handling, and a repeated auto-reply. They are not a quality score over unknown scenarios.

**Dataset decision check:** generated the supplied 5 categories, 50 merchants, 200 customers, and 100 triggers, pushed all **355 contexts** into a fresh local database, and independently tried the supplied **30 test pairs** at the dataset's simulated `2026-04-26T10:00:00Z`. Each pair got a fresh sent/conversation state to prevent a prior pair suppressing it. The service returned a valid action on **15/30** and no action on **15/30**. Of the no-action cases, **13** have `payload.placeholder: true` and therefore supply no usable event facts; **T07** is a pharmacy refill with channel `whatsapp_via_son` rather than direct WhatsApp; **T18** is a festival event 188 days away, beyond our 45-day relevance window. Thus **15/17 factual scenarios generated a message**, while the two other factual scenarios were intentionally held back. This is coverage under our rules, **not a 15/17 accuracy claim**: the judge might rate some of those messages poorly and may interpret abstentions differently.

**Deployed service:** previous live checks returned HTTP 200 for health, metadata, an empty tick, and demo previews. A live performance-dip preview reported that the AI rewrite was applied; other sampled previews fell back to built-in wording. We have not run the official LLM scoring simulator with a judge-side API key. The key configured privately on Render cannot be assumed to be available to our local scoring script.

**Time caveat:** the supplied sample events mostly describe April–June 2026, whereas today's real date is September 2026. The 30-pair check deliberately used the dataset's April simulated clock. If somebody runs the supplied simulator unchanged today, its clock uses the current UTC time and most old triggers will correctly be expired, giving a misleading quality comparison. The competition API uses the `now` value sent on each judge tick.

## Original improvement plan from 26 September (progress recorded below)

1. **Make the evaluation trustworthy.** Create a controlled test run with the judge's simulated clock, fresh state, measured response time, and a table of all 30 cases. If a scoring key is available to a local judge, use the provided LLM simulator to obtain scores by dimension. Keep judge scoring separate from our service-pass rate.
2. **Protect the evaluation run.** The current `render.yaml` stores SQLite at `/tmp/vera.sqlite3`; that file can disappear on instance replacement or redeploy. Move judge state to durable storage before relying on it through restarts, then rehearse warmup and a full hour of ticks. Check free-host cold-start behavior against the judge's five-second health request and 30-second action timeout.
3. **Improve the actual message quality.** Make each trigger branch use a sharper, verified fact from the specific merchant and category: relevant digest details, comparable peer metrics only with the right population, an active offer only when valid, and a concrete reason to act now. Give dentist, salon, restaurant, gym, and pharmacy messages their own tone. Tune on the five judge dimensions, not on how fancy the website looks.
4. **Strengthen factual validation.** The current AI validator accepts any number that appears anywhere in the supplied context, so a number could be real but tied to the wrong fact. Validate named claims against the exact approved fact record; check expired offers and dates; add adversarial tests. Do not claim zero hallucinations based on the current regex checks.
5. **Deepen conversation handling.** When someone says YES, give the useful draft immediately and tailor it to the specific ask; handle genuine questions, Hindi-English replies, negative sentiment, and follow-up state without repeating text. Check one complete conversation per category.
6. **Make judging and demo behavior legible.** Show which fact supported a message, why a trigger was skipped, and whether AI truly changed the wording. Keep the demo separate from the judge's stored state, and add cases that visibly demonstrate both sending and safely abstaining.

### Current limitations and next decision

The submitted base URL is `https://magicpin-vera-bot-06ct.onrender.com`, backed by the private GitHub repository `Hisham1920/magicpin-vera-bot`. The submitted URL can be changed, but code changes do not require a new URL if the same service is redeployed. The current demo displays bundled synthetic data, while actual judge contexts arrive through the API. AI wording is optional, only attempted for up to two actions per tick, and may fall back.

## 26 September, later session — reliability upgrade in progress

- Confirmed Render's free web-service filesystem is temporary: the `/tmp/vera.sqlite3` file is deleted when the service spins down, restarts, or redeploys. Render's free Postgres survives *web-service* restarts but expires 30 days after database creation. This is a short challenge-window solution, not indefinite archival.
- Added `storage.py`. On a laptop, `VERA_DB` still selects a SQLite file. When Render supplies `DATABASE_URL`, the same six tables and query paths use a Postgres connection. The code fails visibly if a configured Postgres database cannot be reached; it does not silently discard judge state into SQLite.
- Updated `render.yaml` to define the free `magicpin-vera-state` Postgres service and inject its internal connection string, added the Postgres client dependency, and exposed `storage_backend` in health so deployment can be checked without revealing the connection string.
- Added `tests/test_restart.py`, which starts two independent Python processes against one SQLite file. The second sees all pushed contexts and does not resend the same trigger. **7/7 local tests pass.** This proves the local restart scenario; the actual Postgres path still needs a live deployment check.
- Commit `8b450fe` deployed successfully through the existing Render Blueprint. The Blueprint created the free `magicpin-vera-state` database and linked its private connection URL. After the Blueprint rollout, the same public `/v1/healthz` returned HTTP 200 and `"storage_backend":"postgresql"`.
- Sent **only the supplied synthetic dentists category, version 1**, through the public `/v1/context` endpoint. The response accepted it, and health showed one category stored on Postgres. No merchant, customer, or trigger test records were sent to the deployed service.

**Live restart check: passed.** A documentation-only commit (`4353643`) caused Render to replace the web-service process. Its new health response showed a fresh uptime of 22 seconds, `"storage_backend":"postgresql"`, and the same one stored dentists category. The category was saved before this redeploy, so this verifies web-service replacement did not erase the Postgres data. The other judge contexts remain empty until the evaluator pushes them. A free database still expires after 30 days, and the free web service may take 50 seconds or longer to wake from idle. This check did not yet measure the official judge score or simulate a database outage.

## 27 September — measuring message quality, step 2

**What we found:** Magicpin included a local `judge_simulator.py`. It can use Gemini or OpenAI as the *practice judge*. The choice of judge model does not change which model our bot uses to write messages. The simulator prints a number out of 50 and also displays that number divided by 50 as a percentage. That percentage describes the judge's opinion of message quality, not a tested accuracy rate.

**Baseline completed:** We copied their scoring script without modifying it. We chose the same 15 fact-backed cases from the supplied 30 pairs, covering all five business categories. The deployed server used the existing private OpenAI key and `gpt-4.1-mini` as the *practice judge* to rate the bot's built-in messages. It saved each score and explanation. Failed AI calls are excluded. The read-only scorecard is at `/demo/evaluation`.

| Baseline measure | Score |
| --- | ---: |
| Average total across 15 messages | **34.47 / 50** |
| Uses concrete facts | 7.00 / 10 |
| Sounds right for the kind of business | 7.53 / 10 |
| Fits this particular business | 7.13 / 10 |
| Explains why the message arrives now | 6.73 / 10 |
| Makes the person want to reply | 6.07 / 10 |

**How to read this:** An AI judged *fifteen built-in drafts*, not all possible customer and merchant actions. The website may show an optional AI rewrite on top of those drafts, and the challenge company may judge different messages with a different model. So **34.47/50 is a practice score, not an official challenge score or 68.94% accuracy.** The honest answer to “what accuracy have we reached?” is still “we do not have a labeled official accuracy measure.”

**Why the low-scoring messages were weak:** The webinar message only named a webinar, leaving out its date, credits, and attendance fee even though they were supplied. The salon question ignored a recorded 20% rise in calls. The gym follow-up did not mention that the customer previously focused on weight loss. These are gaps we can fix using existing facts.

**Where the scoring code lives:** `challenge_judge.py` is the original judge's scoring script. `judge_eval.py` picks 15 repeatable examples, calls that scorer, and saves the result in Postgres as it progresses. In `app.py`, startup launches one run when a new run ID is chosen; `GET /demo/evaluation` lets us read its progress and results. `engine.py` writes the draft message being tested. `render.yaml` names the evaluation run and model. The private key is an environment value on Render and never appears in a project file. `tests/test_message_improvements.py` checks that new claims are drawn from supplied facts. The first baseline is saved separately so we can compare it with the second run.

**What we changed for the second run:** We added webinar details from the category calendar, included an observed call trend only when the merchant record supplies it, and made the gym follow-up refer to the customer's recorded goal. We also make a dentist's greeting say `Dr.` only if that exact name already appears in the merchant name. We kept the same 15 sample cases and judge model so the before-and-after comparison is understandable. The score may still vary between AI calls; a difference in one small sample is not proof of better performance on unseen cases.

**Second run completed:** The new drafts averaged **36.47/50** across the same 15 cases, an increase of **2.00 points out of 50**. All 15 were scored successfully in both runs. The baseline and revised JSON reports are saved separately, so you can read every message and the judge's explanation.

| Dimension | Before | After | Change |
| --- | ---: | ---: | ---: |
| Concrete facts | 7.00 | 7.47 | +0.47 |
| Category voice | 7.53 | 7.67 | +0.14 |
| Merchant fit | 7.13 | 7.73 | +0.60 |
| Why now | 6.73 | 7.07 | +0.34 |
| Likelihood of reply | 6.07 | 6.53 | +0.46 |

**A real example:** The old webinar text told Dr. Meera the webinar's name and offered a summary. The new version gives the event date, **2 CDE credits**, and the price rule **free for IDA members, ₹500 otherwise**, all from the supplied category calendar. That one case went from **21/50 to 36/50**. The salon question gained the verified **20% call rise** and went from **26/50 to 37/50**. A customer gym reminder used her recorded **weight loss** focus and went from **29/50 to 35/50**.

**The uncertainty in those numbers:** Some *unchanged* messages received different scores across the two calls, including the restaurant match-day message (35 then 32). AI judges are variable. The evidence supports a better result on this practice set, particularly in the revised weak cases, but it does not prove the same gain on secret tests or reveal the official score. The scorecard evaluates `engine.py`'s built-in draft messages. It does not score the optional `writer.py` rewrite, a full hour of judge ticks, customer conversations, abstentions, or API latency. The model judged the supplied synthetic facts as given; we did not independently verify the dataset's webinar and compliance claims.

**What you can do next:** Open `/demo/evaluation` for the latest live report. The saved `vera_baseline_scorecard.json` and `vera_improved_scorecard.json` preserve the earlier message bodies and five scores case by case. We can next test the complete API through the simulator with a private judge key, and decide whether a Gemini comparison is worth the extra account and cost. Our bot does **not** need Gemini just because other people chose it to *grade* their local runs.

## 27 September — making the messages fit each merchant, step 3

**The simple idea:** A good message answers three small questions: *Who is this for? What actually happened? What useful thing can they do next?* The answers must come from the supplied data. If a fact is missing, we leave it out instead of guessing. This matters more than fancy wording.

| Business type | Example of a more personal message | Fact we deliberately do not assume |
| --- | --- | --- |
| Dentist | Bharat's Andheri West practice has a recorded 50% call decline; its listing is marked unverified. Offer a listing checklist and patient-friendly post draft. | We cannot say the unverified listing **caused** the decline. |
| Salon | Studio11's calls rose 20% in the last seven days. Ask which service customers are requesting so its owner can get a relevant post draft. | We cannot claim a specific salon service caused the rise. |
| Restaurant | The Delhi IPL match has a supplied time; SK Pizza Junction is in Sant Nagar. Offer a pizza post with menu details the owner confirms. | Its Tuesday–Thursday promotion is **not** advertised for a Sunday match. |
| Gym / yoga studio | Rashmi preferred weekday evenings and previously focused on weight loss. Offer to **check** options for returning. | Her old membership does not prove she qualifies for the currently advertised free trial. |
| Pharmacy | The seasonal update lists rising demand for ORS, sunscreen and antifungal items, and falling demand for cold and cough products. Offer an Apollo stock-check draft. | Demand trends do not prove this pharmacy actually has those products in stock; a trend code does not explicitly state percentage units. |

**What changed in the code:** In `engine.py`, `compose()` now adds useful details only to the matching event type. For example, a match includes its stated time, a milestone uses the actual review number, and a reminder uses the customer's consent and recorded preferences. `recall_slot()` checks a proposed slot against the supplied tick time; if the slot has passed, the message does not offer it. `plain_window()` turns `7d` into “7 days,” and `trend_topics()` reads the supplied up/down direction without inventing a percent sign. The main `/v1/tick` path in `app.py` passes the judge's simulated time to `compose()`, so the expiry guard uses the judge's clock.

**What changed at the submitted URL:** The original URL, `https://magicpin-vera-bot-06ct.onrender.com`, stays the same. Render deploys commits from our connected GitHub branch to that address. On the homepage, `web/index.html`, `web/style.css`, and `web/app.js` now explain the three bot steps and load the latest practice score with its **five** component scores. A link opens the detailed per-message feedback at `/demo/evaluation`. The homepage and API documentation describe the demo; the challenge's five `/v1/*` endpoints still serve the evaluation. A live check returned HTTP 200 for the homepage and health endpoint, showed Postgres as storage, and returned the completed final scorecard.

**Measured results, same 15 synthetic cases and same OpenAI practice judge:**

| Dimension (each out of 10) | Previous round | Final merchant-specific round |
| --- | ---: | ---: |
| Concrete, checkable facts | 7.47 | **8.07** |
| Right voice for the business type | 7.67 | **8.00** |
| Fit for this particular merchant | 7.73 | **7.93** |
| Reason to message now | 7.07 | **7.47** |
| Would they reply? | 6.53 | **6.67** |
| **Total out of 50** | **36.47** | **38.13** |

38.13/50 means **76.26% of available practice rubric points**. It clears our informal 35/50 target (70% of points). It does **not** mean 76.26% accuracy, a guaranteed score floor, or an official result. An intermediate run after the first batch of edits scored 36.40/50; we examined its weak cases, revised the wording and ran the same 15 messages again. AI scores fluctuate: the salon question kept the same text and score, while another unchanged message received a different score. On the final comparison, the kids-yoga planning case dropped one point and several others improved. All five average dimensions improved, but the sample is small and the judge may use another model.

**Regression check after the final score:** `python3 -m unittest discover -s tests -v` passed **15/15**. These tests cover API behavior, saved state across a restart, opt-out and duplicate suppression, missing facts, offers that do not fit an event, and past appointment slots. `node --check web/app.js` and Python compilation also passed. The live deployed scorecard returned `status: complete`, `scored: 15`, and average `38.13`.

**Next work, led by accuracy:** First, test the complete API with simulated time, context updates, multiple ticks and replies; this practice score only evaluates built-in draft messages. Second, improve factual checks on optional AI rewrites so a number cannot be borrowed from the wrong field. Third, test one complete YES/NO/STOP conversation for each category and check that the draft fulfils the promise in its first message. Fourth, address free-host wake-up delays before a time-limited real judge run. Keep the five-part practice scorecard for comparisons, but use the company's own feedback as the final signal when available.

## Full bot and conversation check — 27 September

**Picture the two jobs separately:** When the judge sends a tick, Vera decides whether there is enough evidence to start a conversation. When a recipient replies, Vera must answer *that specific reply*. A strong first message is not enough if the next answer repeats itself, makes up a fee, or ignores STOP.

### What I actually ran

`full_bot_check.py` starts the actual HTTP server on the laptop with a fresh temporary database and no model key. It generates and sends all supplied synthetic records through `POST /v1/context`: 5 categories, 50 merchants, 200 customers, 100 triggers. It uses the challenge's simulated clock, **26 April 2026 at 10:00 UTC**, because today's real date would make old sample events appear expired. It checks every one of the 30 supplied pairs independently, ticks all 100 triggers at several times, updates one category record, sends YES and STOP replies, then restarts the server to test whether the stop decision survives. It does **not** touch the database at the submitted URL.

| Local functional check | Result | What it means |
| --- | --- | --- |
| 30 supplied send/skip pairs | 15 sends, 15 skips | Matched the expected action counts for those sample cases; these cases alone do not determine official accuracy. |
| All 100 triggers, first tick | 13 sends across all five categories | The bot found eligible actions while respecting one message per recipient and the tick limit. |
| Same time, five minutes later | 0 and 0 new sends | Repeated ticks did not send duplicates. |
| After 61 minutes | 7 more eligible actions; no repeated suppression keys | Another eligible event for a recipient can be considered after the cooldown. |
| Updated category digest | 1 new action including the new fact | The newer version is used when drafting. |
| YES, Hindi-English cost question, customer YES | Each produced a distinct answer | The merchant receives an event-specific draft; a cost question states the price is unconfirmed; the customer receives a named draft. |
| STOP, repeat STOP, later tick, restart | Ended, stable answer, 0 future sends after restart | Opt-out survives a process restart. |
| Warm local HTTP `/v1/tick` | 15.0 ms at the 95th percentile of 36 calls; maximum 18.3 ms | This is local, with the AI key disabled; it says nothing about a free hosted server waking up or remote AI latency. |

**The bug this caught:** A merchant could reply YES to a pharmacy alert and receive a broad summary. If they then asked, “Kitna cost hoga?”, the bot tried to send the *same* summary again, hit its no-repeat guard, and ended the conversation. Now `app.py` checks intent first, uses `engine.py` to write a stock-check draft after YES, and uses a separate `answer_question()` answer when cost is unknown. A customer saying “Haan, details bhejo” gets a named, event-specific draft. We do not claim that stock was checked, a price is approved, or an appointment was booked.

**Five files to know:** `app.py` routes the reply and records STOP; `engine.py` writes the event-specific draft and answers questions; `writer.py` optionally polishes only an approved outgoing message; `demo.py` previews those same reply decisions using bundled examples; `web/app.js` shows the interactive chat. `full_bot_check.py` exercises the actual API instead of only previewing a page. The tests in `tests/test_reply_quality.py` and `tests/test_writer_guard.py` focus on the conversation and factual boundaries. The website now has one-click examples for YES, a question, Hindi-English, and STOP. Pressing STOP closes its simulated input.

**What changed in optional AI wording:** Before sending an approved first message, `writer.py` can request nicer wording. The request supplies the approved draft as the *only fact source*; names and tone can help address it. The validator rejects changed or missing number tokens, missing named offers and source titles, new links, ungrounded “free” or “best” claims, changed up/down direction, and missing recipient names or YES/STOP choices. If it rejects a rewrite or the model is unavailable, Vera sends the original grounded message. Automated checks deliberately try to attach the same price to a different service. These guards reduce common errors; they cannot mathematically prove all rewritten text true.

**Results and limits:** The full local HTTP check passed and `python3 -m unittest discover -s tests -q` passed **24/24**. The earlier **38.13/50** remains the most recent practice *message quality* score. We have not rescored those 15 first messages, which the conversation improvements do not change, and do not have an official accuracy score. The full HTTP check disables the optional AI key to isolate base behavior; local response times cannot predict free hosting cold starts or external model calls. Hidden judge cases may differ from the supplied synthetic cases.

**Next accuracy work:** Compare official judge feedback when available, especially multi-turn conversations and opt-out edge cases. Then exercise model rewrites against deliberately misleading *realistic* offers and dates with the configured model, while tracking how often fallback is used. Separately measure public endpoint wake-up time and check that the hosted application uses persistent storage before a timed judging window.

## 28 September — checking AI fact swaps and public timing

**The easy version:** Imagine a dentist has a ₹199 competitor offer and a ₹299 own offer. The old check could see both prices in an AI rewrite and think everything was fine, even if the AI swapped which clinic offered which price. We found four examples of this kind of mistake that the old check accepted: exchanged appointment dates, exchanged competitor and own prices, a call-growth percentage attached to an offer instead, and an unverified Google listing described as verified.

In `writer.py`, the model is now told to keep factual sentences exactly as written and polish only the greeting or next-step question. `valid()` checks that sentences containing dates, numbers, offers, statuses, or trends remain attached to the same subject. It also rejects added sentences and common invented cause or completed-action claims, such as saying the listing *caused* the decline or that we already *fixed* it. If a proposed rewrite fails, Vera returns the original message. This is intentionally cautious: more AI rewrites may fall back, but the grounded message still goes out. It is a rule-based safeguard, not a proof that every possible claim is true. `tests/test_writer_guard.py` contains the examples and a simulated model response showing the fallback. A safe change to a call-to-action still passes.

**Local result:** All **30 automated tests passed**. The isolated full HTTP bot check also passed again: 15 sends and 15 skips for the 30 supplied pairs, no duplicate sends on immediate repeated ticks, and YES, Hindi-English question, customer YES, STOP, and restart behavior remained intact. These are behavior checks, not the official score. The latest separate first-message practice score remains **38.13/50** because the grounded drafts did not change.

**Live result before this code deploy:** The submitted `/v1/healthz`, `/v1/metadata`, homepage, and read-only synthetic demo returned HTTP 200. Health reported PostgreSQL and metadata reported `gpt-4.1-mini`. One AI preview accepted different wording for a restaurant example; another preview kept the grounded dentist message. `ai_used: false` does not say whether the model failed, timed out, produced the same text, or failed validation, so it is not an acceptance-rate measurement.

**Timing detail:** Individual public requests from this workspace took roughly 7–11 seconds. A connection-reuse check isolated about **9.0 seconds for the first TLS setup** on this route, while two requests reusing the connection took **0.125 and 0.108 seconds total**. The first health response said the service had already been running for 768 seconds. Therefore these numbers show our network path and a warm app; they cannot establish a Render cold-start time or prove the five-second judge health target is safe. Render's free web service may sleep after inactivity, so a separate idle-then-request measurement is still needed.

**Current links:** The public repository is `Hisham1920/merchant-intelligence-assistant`; the challenge URL remains `https://magicpin-vera-bot-06ct.onrender.com`.

**Later, for freelancing:** This demo already shows a useful pattern: a company supplies approved business facts, Vera decides whether a message is appropriate, and a person reviews a draft. A client-ready version would need each company's own data, explicit customer permission, actual channel integration, approval before sending, monitoring, and a durable paid database. The competition website itself is a demonstration, not a live WhatsApp automation sold to a business.
