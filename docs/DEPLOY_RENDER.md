# Deploy the backend to Render

The backend is a FastAPI + LangGraph + Playwright + Chroma + SQLite service.
Render is a good fit because it supports native Docker deploys with a
persistent disk — which is what we need for SQLite + the Chroma vector
store + artifact screenshots.

## Why not the free tier?

Playwright's headless Chromium plus the sentence-transformers embedding
model need more than 512 MB of RAM. The smallest Render plan that works
reliably is **Standard** (2 GB RAM, ~$25/mo at time of writing). If you
want to run on Starter (512 MB), set `EMBEDDINGS_PROVIDER=hash` (hashing
fallback) and expect slower / flakier scans.

## 1-minute deploy via Blueprint

1. Push this repo to GitHub (already done on branch
   `claude/build-accessibility-remedia-6sVZ8`).
2. Go to <https://dashboard.render.com/blueprints> → **New Blueprint**.
3. Connect GitHub → pick `francolinx/CCWCAG` → choose the branch.
4. Render reads [`render.yaml`](../render.yaml) at the repo root and proposes:
   - a **Web Service** (Docker, from `backend/Dockerfile`)
   - a **5 GB persistent disk** mounted at `/data`
   - env vars pre-filled (Playwright headless, embeddings, model name)
5. Click **Apply**. Render builds the Docker image (this installs Chromium
   + Python deps + runs the WCAG ingest — allow 5–10 minutes for the
   first build).
6. When it goes live, note the URL, e.g. `https://accessibility-remediation-copilot-api.onrender.com`.

## 2. Add the OpenAI key (after the first deploy)

In the Render dashboard for the service → **Environment** → edit
`OPENAI_API_KEY` → paste your **rotated** key → **Save Changes**. Render
will redeploy automatically. Never commit the key.

Verify:

```bash
curl -s https://<your-render-url>/api/config
# expect: "llm_enabled": true
```

## 3. Lock down CORS

Once the Vercel frontend is live, tighten CORS in the Render dashboard:

```
CORS_ALLOW_ORIGINS=https://<your-frontend>.vercel.app
```

(Comma-separate if you have more than one origin.) Redeploy.

## 4. Point the Vercel frontend at it

Open the Vercel URL once with the API query param:

```
https://<your-frontend>.vercel.app/?api=https://<your-render-url>
```

It's cached in `localStorage`, so afterwards you can use the URL without
the `?api=` parameter.

## 5. Smoke test

```bash
curl -s https://<your-render-url>/api/health
# {"status":"ok","env":"prod"}

curl -s -X POST https://<your-render-url>/api/scans \
  -H "content-type: application/json" \
  -d '{"root_url":"https://www.w3.org/WAI/demos/bad/before/home.html","page_limit":3}'
```

Poll `GET /api/scans/{id}` until `status` is `succeeded` / `partial`.

## Troubleshooting

- **Build runs out of memory** → bump the build plan temporarily, or
  pre-build the image locally and push to a registry Render can pull.
- **First scan is very slow** → expected. The Chroma index + Chromium
  warm-up happens on first use and is cached on the persistent disk.
- **Headless Chromium crashes on JS-heavy sites** → increase
  `PLAYWRIGHT_TIMEOUT_MS` (default 45000 in Render config) and consider
  setting `PLAYWRIGHT_NAV_WAIT=domcontentloaded`.
- **Scans return 0 findings from axe** → some sites block headless
  browsers via User-Agent. The current UA is `AccessibilityRemediation
  Copilot/1.0`; override in `backend/app/services/browser.py` if needed.
