# Perplexity prompt — Render backend deploy

> Paste everything between the `===` lines into Perplexity (or Perplexity
> Comet / Copilot). It gives Perplexity enough context to walk you
> through the current Render dashboard UI step-by-step.

===

I need you to walk me, step by step, through deploying the **backend
service** of a GitHub repo to **Render** using the current (2025/2026)
Render dashboard. I want exact click paths, menu names as they appear
today, and the exact values to enter in each field. Assume I am logged
into Render and have already connected my GitHub account.

## Repo details
- GitHub repo: `https://github.com/francolinx/CCWCAG`
- Branch to deploy: `claude/build-accessibility-remedia-6sVZ8`
- The repo already contains a **Render Blueprint** at `render.yaml` at
  the repo root. I want you to have me deploy via
  **Blueprints → New Blueprint Instance**, not via the manual "New Web
  Service" flow, so the YAML is the source of truth.

## What's in `render.yaml`
```yaml
services:
  - type: web
    name: accessibility-remediation-copilot-api
    env: docker
    dockerfilePath: ./backend/Dockerfile
    dockerContext: .
    plan: standard         # 2 GB RAM, 1 vCPU
    region: oregon
    autoDeploy: true
    healthCheckPath: /api/health
    disk:
      name: copilot-data
      mountPath: /data
      sizeGB: 5
    envVars:
      - key: APP_ENV            { value: prod }
      - key: PLAYWRIGHT_HEADLESS { value: "true" }
      - key: PLAYWRIGHT_TIMEOUT_MS { value: "45000" }
      - key: PLAYWRIGHT_NAV_WAIT   { value: networkidle }
      - key: EMBEDDINGS_PROVIDER   { value: local }
      - key: EMBEDDINGS_MODEL      { value: all-MiniLM-L6-v2 }
      - key: MODEL_PROVIDER        { value: openai }
      - key: MODEL_NAME            { value: gpt-4o-mini }
      - key: OPENAI_API_KEY        { sync: false }   # I set this in the dashboard, never in YAML
      - key: CORS_ALLOW_ORIGINS    { value: "*" }    # I'll tighten to my Vercel URL later
      - key: DEFAULT_CRAWL_DEPTH   { value: "1" }
      - key: DEFAULT_PAGE_LIMIT    { value: "5" }
```

## What the service actually is
- **FastAPI + LangGraph + Playwright (headless Chromium) + Chroma
  vector store + SQLite + Pillow screenshot annotation.**
- Built via `backend/Dockerfile` which installs Chromium with
  `python -m playwright install --with-deps chromium`, runs
  `scripts/ingest_wcag.py` at build time to populate the Chroma vector
  store, and starts `uvicorn backend.app.main:app` honoring `$PORT`.
- Needs a **writable persistent disk at `/data`** for the SQLite DB, the
  Chroma vector store, and screenshot artifacts. `render.yaml` asks for
  a 5 GB disk.
- **RAM required ≈ 2 GB** because of Chromium + sentence-transformers.
  Render's Standard plan (2 GB, ~$25/mo) is the minimum that works
  reliably. Free/Starter (512 MB) will OOM.

## What I need from you
1. Walk me through the current Render dashboard to **create a Blueprint
   Instance** from this repo: which top-nav item, the exact wording of
   the "Connect a repository" screen today, how to pick the correct
   branch (`claude/build-accessibility-remedia-6sVZ8`, not `main`), and
   what the confirmation screen that lists "1 Web Service + 1 Disk"
   should look like.
2. Confirm the Standard plan is still the right choice for a
   Chromium + local embeddings workload in the **current** Render
   pricing. If they've renamed tiers (e.g., "Starter Plus", "Standard
   Plus") tell me the current name and price.
3. After the initial apply, the build will take 5–10 minutes (Docker
   layer with Chromium + Python deps + WCAG ingest). Tell me:
   - Where to watch build logs in the current UI.
   - What a healthy "Live" status looks like.
   - How to find the generated `*.onrender.com` URL.
4. Walk me through adding the **`OPENAI_API_KEY`** secret through the
   dashboard only (never in the YAML, never in git). Exact tab name,
   exact field, where to paste, and confirm it triggers an auto
   redeploy.
5. Smoke tests to run after redeploy (give me curl commands I can paste
   into my terminal):
   - `GET /api/health` → `{"status":"ok","env":"prod"}`
   - `GET /api/config` → `llm_enabled: true`
   - `POST /api/scans` against
     `https://www.w3.org/WAI/demos/bad/before/home.html` with
     `page_limit: 3`, then `GET /api/scans/{id}` until `succeeded` /
     `partial`.
6. Once my Vercel frontend is live at some `*.vercel.app` URL, walk me
   through **tightening CORS** by editing `CORS_ALLOW_ORIGINS` in the
   Environment tab (replacing `*` with the Vercel URL).
7. Cover these failure modes with concrete current-UI remediation steps:
   - Build OOM on Standard → temporary Pro bump, then scale back.
   - Playwright "Target closed" on JS-heavy sites → raise
     `PLAYWRIGHT_TIMEOUT_MS` / switch `PLAYWRIGHT_NAV_WAIT` to
     `domcontentloaded`.
   - `llm_enabled` stays `false` after setting the key → "Clear build
     cache & deploy".
   - 502 Bad Gateway → where the crash log lives in the Logs tab today.
8. Tell me how to **suspend** the service from the current UI when I'm
   not demoing (to save the ~$25/mo) and how to resume it — and confirm
   the `/data` disk persists across suspend/resume.

Please cite the current Render docs pages you rely on and prefer
up-to-date sources over blog posts older than 2024. Keep the tone
concrete and copy-paste friendly — no generic "go to settings" hand
waves. I care about exact field names because the dashboard UI keeps
shifting.

===
