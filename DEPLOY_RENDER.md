# Get one public URL for the bot and website

This project serves the demo website at `/` and the challenge endpoints at the same URL. Deploy the **whole folder**, including `dataset/` and `web/`. The judge needs the base URL, such as `https://magicpin-vera-bot.onrender.com`; do not submit `/` or `/v1/healthz` as the base URL.

## Fast route: GitHub + Render

1. Extract the supplied project ZIP. Create a new GitHub repository, for example `magicpin-vera-bot`. Use GitHub **Add file → Upload files** and drag in the **contents** of the extracted `magicpin-vera-bot` folder. Check that `render.yaml` and `app.py` appear at the repository root, then commit. GitHub browser uploads sometimes make folder dragging awkward; if `web/` or `dataset/` is missing, use the command route below.
2. Open Render Dashboard → **New → Blueprint**. Connect the GitHub repository. Choose the repository and confirm the Blueprint named by `render.yaml`.
3. When Render requests `VERA_CONTACT_EMAIL`, enter your actual submission email. When it requests `OPENAI_API_KEY`, paste your OpenAI API key **there**. Set `OPENAI_API_KEY` to an empty value if you cannot use the key yet; deterministic responses still work. Do not commit the key to GitHub or put it in the website.
4. Create the service and wait for the deploy to finish. Copy the public `https://...onrender.com` URL shown by Render. On a free service, the first request after inactivity can take longer to wake up.
5. Open these URLs in a browser: base URL for the interactive website, then `/v1/healthz` for `"status":"ok"`, then `/v1/metadata` to confirm your name, email, and model.
6. Submit the **base public URL** to the challenge. The evaluator itself pushes the category, merchant, trigger, and customer context; `contexts_loaded` can correctly be zero before its first push.

## If browser upload drops folders: Git command route

From a terminal in the extracted `magicpin-vera-bot` folder, run the following after you create an empty GitHub repository. Replace `YOUR_USERNAME` with your actual GitHub username:

```bash
git init
git add .
git commit -m "Build Vera merchant assistant"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/magicpin-vera-bot.git
git push -u origin main
```

For Windows PowerShell these commands are the same. GitHub may request login via browser or a token; do not paste credentials into this chat.

## Operational note

The included Render Blueprint uses a free web service and a SQLite file at `/tmp/vera.sqlite3`. The file is ephemeral: Render restart or redeploy clears conversation state. During one uninterrupted judging run, state is kept; for robust production use add persistent storage. Free services can sleep when idle, so visit `/v1/healthz` shortly before judging. Use **one worker** so SQLite and in-process locks see the same conversations. AI calls are optional and fall back to grounded wording if they time out or fail a factual check. There is no WhatsApp sending or Google publishing integration; the judge consumes the JSON actions.
