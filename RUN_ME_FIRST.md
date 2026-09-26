# Running the Vera bot on your Windows laptop

1. Unzip this project. Open the **magicpin-vera-bot** folder in VS Code.
2. Open **Terminal → New Terminal**. Make sure the terminal is inside the folder with `app.py`.
3. In PowerShell, run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8080
   ```

4. Keep that terminal open. Visit `http://127.0.0.1:8080/` to use the demo website. Visit `http://127.0.0.1:8080/v1/healthz` to check the bot. A fresh bot should show status `ok` and four zero context counts. The judge will load its own context during evaluation.
5. For a quick contract check, open a **second** VS Code terminal in the same folder and run:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```

6. Generate the complete practice dataset if you want to inspect the 30 pairs:

   ```powershell
   .\.venv\Scripts\python.exe dataset\generate_dataset.py --seed-dir dataset --out expanded
   ```

The health page proves the server is running locally; it does **not** make the bot reachable from the public internet. Follow `DEPLOY_RENDER.md` for the public URL. Do not put an API key into source code or send it in chat. The bot also runs without an AI API key.

Files to know: `app.py` handles judge requests and saved state; `engine.py` decides what to say; `tests/test_service.py` checks the important behaviors. `dataset/` is the challenge data supplied by magicpin.
