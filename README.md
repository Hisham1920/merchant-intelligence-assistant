# Merchant Intelligence Assistant (Vera)

[Try the live demo](https://magicpin-vera-bot-06ct.onrender.com) · [API documentation](https://magicpin-vera-bot-06ct.onrender.com/docs)

Vera is an AI-assisted merchant engagement prototype built for the magicpin AI challenge. It uses supplied business and event context to decide when to send a relevant WhatsApp-style message, when to stay quiet, and how to handle YES, questions, Hindi-English replies and STOP. The website has 10 interactive synthetic scenarios. It does **not** send real WhatsApp messages, book appointments, or change a merchant's Google profile.

The service exposes five `/v1/*` endpoints for the challenge's context, tick, reply, health and metadata calls. In an isolated local HTTP check it loaded 355 synthetic contexts, replayed 30 supplied send/skip pairs, exercised timed ticks and reply handling, and passed 24 automated tests. The separate 38.13/50 figure shown on the site is an OpenAI **practice message-quality rubric**, not an official accuracy score.

## Approach

- `app.py`: five required `/v1/*` endpoints, atomic context version updates, per-recipient suppression, and conversation handling.
- `storage.py`: SQLite on a laptop; PostgreSQL when `DATABASE_URL` is set. The Render Blueprint provisions a free Postgres database and injects its private connection URL.
- `engine.py`: deterministic message composer using supplied trigger facts, category digests, merchant offers, and customer consent. Placeholder triggers, missing facts, expired events, and unconsented customer sends are skipped.
- `writer.py`: optional OpenAI wording rewrite of eligible messages with fact checks and automatic fallback. Set `OPENAI_API_KEY` privately on the host; default model is `gpt-4.1-mini`.
- `demo.py` and `web/`: interactive scenario previews and a conversation mockup. Preview data is synthetic and does not overwrite judge state.
- First outbound actions include a mock template name and parameters. A YES reply creates a reviewable draft; it never claims to have published or sent the draft.
- A repeated auto-reply is ended; STOP and not-interested requests end and suppress further proactive sends. Only one proactive send per recipient per tick, capped at 20 actions. Follow-ups do not repeat the initial message.

## Local run

Install: `python -m pip install -r requirements.txt`

Start: `python -m uvicorn app:app --host 0.0.0.0 --port 8080`

Check: `http://localhost:8080/` for the website, `http://localhost:8080/v1/healthz` for the API, and `python -m unittest discover -s tests -v`.

Run the complete isolated HTTP check: `python full_bot_check.py --output full_bot_report.json`. This loads the supplied synthetic data into a temporary database, replays all 30 supplied sample pairs, simulates multiple timed ticks, tests YES/questions/STOP and a restart, then writes a JSON report. Its fixed test clock is `2026-04-26T10:00:00Z`; the local run disables the optional model, so its millisecond timings do not predict hosted cold starts or model latency. These checks measure service behavior, not the unknown official judge score.

Generate additional practice records with `python dataset/generate_dataset.py --seed-dir dataset --out expanded`. Deploy with [`DEPLOY_RENDER.md`](DEPLOY_RENDER.md) and `render.yaml`. Set `VERA_TEAM_NAME`, `VERA_MEMBER_NAME`, and `VERA_CONTACT_EMAIL` before submission; use a **single server worker**. `/v1/healthz` reports `storage_backend` so you can verify the deployed service uses PostgreSQL. If the configured database is unavailable, the service fails rather than silently writing judge state to a temporary SQLite file.

For the existing challenge submission, the public URL is `https://magicpin-vera-bot-06ct.onrender.com`. Its Render Blueprint connects the web service to `magicpin-vera-state`; check `storage_backend: postgresql` before relying on durable judge state.

## Tradeoffs and useful missing data

The rule-based message remains available if the optional AI request fails. It abstains on generated dataset `placeholder: true` triggers rather than claiming an event took place. The most useful extra context would be approved offers, real appointment availability, verified sources for digest items, and permission to publish a draft after merchant approval. For a fresh deployment, set the team contact email privately on Render.
