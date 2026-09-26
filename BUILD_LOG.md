# Vera bot — live build log

**Goal:** Submit one public URL for a working merchant assistant. The same Python service must show a usable demo website and answer the five HTTP calls in magicpin's challenge brief.

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
- [ ] Put the project in GitHub, deploy it, enter the private API key in Render, and submit the public URL.

## Files to know

| File | What it does |
| --- | --- |
| `app.py` | Receives judge requests, remembers conversations, serves demo routes |
| `engine.py` | Decides and writes grounded messages and first reply drafts |
| `web/` | Demo webpage files |
| `tests/` | Checks endpoint and messaging behavior |
| `dataset/` | Magicpin's supplied synthetic practice data |
| `render.yaml` | Hosting settings for Render |
| `DEPLOY_RENDER.md` | Exact steps to get the public URL |
| `writer.py` | Optional OpenAI rewrite with safe fallback |

## Current limitation

The bot has no public URL until the GitHub repository is connected to Render. The AI rewrite requires an API key added privately in hosting settings; the built-in wording works without one. One website scenario intentionally stays quiet because eligible customer consent/facts are missing. The supplied expanded dataset also contains placeholder events with no real event facts; we skip them. Check the real deployed URL before submission.
