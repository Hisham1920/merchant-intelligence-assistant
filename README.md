# Vera challenge bot — working website and API

Open `/` for an interactive website with 10 supplied scenarios. The same service accepts category, merchant, trigger, and customer JSON from the judge at five `/v1/*` endpoints. It selects a grounded trigger, returns a WhatsApp-style message or stays quiet, and handles replies. It does **not** send real WhatsApp messages or change a merchant's Google profile.

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

Generate additional practice records with `python dataset/generate_dataset.py --seed-dir dataset --out expanded`. Deploy with [`DEPLOY_RENDER.md`](DEPLOY_RENDER.md) and `render.yaml`. Set `VERA_TEAM_NAME`, `VERA_MEMBER_NAME`, and `VERA_CONTACT_EMAIL` before submission; use a **single server worker**. `/v1/healthz` reports `storage_backend` so you can verify the deployed service uses PostgreSQL. If the configured database is unavailable, the service fails rather than silently writing judge state to a temporary SQLite file.

## Tradeoffs and useful missing data

The rule-based message remains available if the optional AI request fails. It abstains on generated dataset `placeholder: true` triggers rather than claiming an event took place. The most useful extra context would be approved offers, real appointment availability, verified sources for digest items, and permission to publish a draft after merchant approval. The public deployment URL and your team contact email must be filled in on Render.
