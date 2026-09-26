# Get one public URL for the bot and website

This project serves the demo website at `/` and the challenge endpoints at the same URL. Deploy the **whole folder**, including `dataset/` and `web/`. The judge needs the base URL, such as `https://magicpin-vera-bot.onrender.com`; do not submit `/` or `/v1/healthz` as the base URL.

## Fast route: GitHub + Render

1. Extract the supplied project ZIP. Create a new GitHub repository, for example `magicpin-vera-bot`. Use GitHub **Add file → Upload files** and drag in the **contents** of the extracted `magicpin-vera-bot` folder. Check that `render.yaml` and `app.py` appear at the repository root, then commit. GitHub browser uploads sometimes make folder dragging awkward; if `web/` or `dataset/` is missing, use the command route below.
2. Open Render Dashboard → **New → Blueprint**. Connect the GitHub repository. Choose the repository and confirm the Blueprint named by `render.yaml`. It defines a free web service plus a free Render Postgres database named `magicpin-vera-state`.
3. When Render requests `VERA_CONTACT_EMAIL`, enter your actual submission email. When it requests `OPENAI_API_KEY`, paste your OpenAI API key **there**. Set `OPENAI_API_KEY` to an empty value if you cannot use the key yet; deterministic responses still work. Do not commit the key to GitHub or put it in the website.
4. Create the service and wait for the deploy to finish. Copy the public `https://...onrender.com` URL shown by Render. On a free service, the first request after inactivity can take longer to wake up.
5. Open these URLs in a browser: base URL for the interactive website, then `/v1/healthz` for `"status":"ok"` and `"storage_backend":"postgresql"`, then `/v1/metadata` to confirm your name, email, and model.
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

The Blueprint sets `DATABASE_URL` from the Render Postgres connection. Context, sent-history, opt-outs, and conversations survive a **web-service** sleep or redeploy. Local development still uses SQLite. A free Render Postgres database **expires 30 days after creation**, so this is suitable for the short competition run, not indefinite retention. Render's free web service also sleeps after inactivity and may take around a minute to start, so confirm its availability before judging; a database does not remove cold starts. Use **one worker** while the code uses an in-process lock around decisions. Do not expose the database connection string. AI calls are optional and fall back to grounded wording if they time out or fail a factual check. There is no WhatsApp sending or Google publishing integration; the judge consumes JSON actions. At the end of the competition test, remove synthetic judge data according to the challenge's data-retention instructions.

For the **existing submission** at `https://magicpin-vera-bot-06ct.onrender.com`, push this code to the repository already attached to its Blueprint and check that `/v1/healthz` reports `postgresql`. If the Blueprint does not add the database and inject `DATABASE_URL`, do not claim the persistence upgrade is live; inspect the Blueprint sync result and database service first.
