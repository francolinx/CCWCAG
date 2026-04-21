# Deploying the Backend to Render — Copy/Paste Instructions

> Use this as a standalone comment / runbook. Every step is self-contained.

---

## What you're deploying
The **FastAPI + LangGraph + Playwright + Chroma + SQLite** backend from
this repo. It's a real headless-browser pipeline, so it needs a
long-running host with a writable disk. Render fits; Vercel does not
(Vercel is for the static frontend only — see the separate Vercel
instructions).

## Pre-flight checklist
- [ ] You have a rotated **OpenAI API key** ready. Do **not** paste it in
      chat, commits, or files — you'll set it in Render's dashboard.
- [ ] The repo is pushed to GitHub at `francolinx/CCWCAG`, branch
      `claude/build-accessibility-remedia-6sVZ8`.
- [ ] You have a Render account connected to that GitHub org.

## Plan choice
| Plan | RAM | Works? | Notes |
|---|---|---|---|
| Free | 512 MB | ❌ | Chromium + sentence-transformers will OOM |
| Starter ($7/mo) | 512 MB | ⚠️ | Only if you set `EMBEDDINGS_PROVIDER=hash` |
| **Standard ($25/mo)** | **2 GB** | **✅** | **Recommended** |
| Pro | 4 GB | ✅ | Overkill for MVP |

The `render.yaml` blueprint in this repo defaults to **Standard**.

---

## Step 1 — Deploy via Blueprint (recommended)

1. Open <https://dashboard.render.com/blueprints>.
2. Click **New Blueprint Instance**.
3. Click **Connect GitHub** → authorize → pick **`francolinx/CCWCAG`**.
4. Branch selector → **`claude/build-accessibility-remedia-6sVZ8`**.
5. Render detects `render.yaml` at the repo root and shows:
   - Service: `accessibility-remediation-copilot-api` (Docker web service)
   - Disk: `copilot-data`, 5 GB, mounted at `/data`
   - Env vars: `APP_ENV`, `PLAYWRIGHT_HEADLESS`, `MODEL_NAME`, etc.
   - `OPENAI_API_KEY` shown as **Required** — leave it blank for now.
6. Name the blueprint anything you like. Click **Apply**.
7. **Wait 5–10 minutes** for the first build. It does:
   - Installs Python deps
   - Installs Chromium (~150 MB) via Playwright
   - Runs `scripts/ingest_wcag.py` to build the vector store
   - Starts `uvicorn`
8. When the service turns green, note the URL. Format:
   `https://accessibility-remediation-copilot-api-XXXX.onrender.com`

## Step 2 — Add the OpenAI key (dashboard only)

1. Dashboard → service → **Environment** tab.
2. Find `OPENAI_API_KEY` → click the pencil → paste your **rotated** key.
3. Click **Save Changes**. Render redeploys automatically (~1 min).
4. Verify:
   ```bash
   curl -s https://<your-render-url>/api/config
   ```
   Expect `"llm_enabled": true`.

> **Never** commit the key. `.env` is gitignored; `.dockerignore` blocks
> it from the build context.

## Step 3 — Lock down CORS once the frontend is live

By default CORS is `*` for easy testing. Once your Vercel frontend is
deployed, replace it:

1. Dashboard → service → **Environment**.
2. Edit `CORS_ALLOW_ORIGINS` → set to your Vercel URL, e.g.
   `https://accessibility-copilot.vercel.app`
3. Save → auto-redeploy.

## Step 4 — Smoke tests

```bash
# Liveness
curl -s https://<your-render-url>/api/health
# {"status":"ok","env":"prod"}

# Safe public config (must never contain secrets)
curl -s https://<your-render-url>/api/config | jq .

# Start a scan against the W3C "bad" demo page
curl -s -X POST https://<your-render-url>/api/scans \
  -H "content-type: application/json" \
  -d '{"root_url":"https://www.w3.org/WAI/demos/bad/before/home.html","page_limit":3}'

# Poll (replace <id>)
curl -s https://<your-render-url>/api/scans/<id>
# Wait for "status":"succeeded" or "partial"

# Get grouped findings
curl -s https://<your-render-url>/api/scans/<id>/findings | jq '.pages | length'
```

## Step 5 — Open the API docs

`https://<your-render-url>/docs` → Swagger UI with every endpoint.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build OOM | Temporarily set plan to Pro, deploy once, then scale down. |
| First scan is very slow (30–60 s) | Expected. Chromium + Chroma cold start. Cached on `/data` afterwards. |
| Axe returns 0 findings on a real site | Target may block the bot. Override UA in `backend/app/services/browser.py` (line defining `user_agent=...`). |
| Playwright "Target closed" errors | Increase `PLAYWRIGHT_TIMEOUT_MS` (env var) to `60000` and try `PLAYWRIGHT_NAV_WAIT=domcontentloaded`. |
| `llm_enabled=false` after setting the key | Check the env var name exactly (`OPENAI_API_KEY`). Redeploy via **Manual Deploy → Clear build cache & deploy**. |
| 502 Bad Gateway | Open the service's **Logs** tab. Usually a crash during startup — look for Python tracebacks. |
| Rate-limited by OpenAI | Lower `page_limit` on scans; the remediation cache already dedupes per rule_id. |

## Rollback
Dashboard → service → **Deploys** → pick a previous green deploy →
**Rollback**. The SQLite DB and artifacts stay intact on the persistent
disk across rollbacks.

## Cost control
- Pause the service when not demoing (dashboard → **Suspend**).
- The 5 GB disk is billed separately (~$1.25/mo). Shrink to 1 GB in
  `render.yaml` if tight.

---

**Done.** Your backend URL is now:
`https://accessibility-remediation-copilot-api-XXXX.onrender.com`

Next: point the Vercel frontend at it (see the separate Vercel
instructions).
