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

## Improvement plan, in priority order

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

**What we are doing now:** We copied their scoring script without modifying it. We chose the same 15 fact-backed cases from the supplied 30 pairs, covering all five business categories. On the deployed server, a limited background run will use the existing private OpenAI key to judge the bot's built-in messages. It will save each score and explanation so we can find the weak cases before changing any wording. An AI failure or unparseable answer must be marked as an error, never converted to a pretend valid score. The public read-only report will be at `/demo/evaluation`. **Status: evaluation code prepared and locally checked; awaiting deployment and actual scores.**
