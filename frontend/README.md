# Accessibility Remediation Copilot — Frontend

Static demo UI that talks to the FastAPI backend.

## Why this is a separate folder

Vercel's serverless platform can't host the backend:
- Playwright requires a long-running headless Chromium installation that
  exceeds the 50 MB function bundle limit.
- Chroma needs a writable persistent volume; serverless filesystems are
  ephemeral.
- Scans frequently run longer than serverless timeouts.

So this is a **thin static frontend**. It reads the API base from:

1. the `?api=` query string on first load (then caches in `localStorage`), or
2. defaults to the same origin (useful when you run it behind the FastAPI
   backend's `/ui/` route).

## Deploy to Vercel

```bash
# from repo root
cd frontend
npx vercel deploy --prod
```

Or from the Vercel dashboard:

1. New Project → import this repo.
2. Set **Root Directory** to `frontend`.
3. **Framework preset:** `Other` (this is plain static HTML).
4. **Output directory:** `public`.
5. Deploy.

Then open:

```
https://<your-vercel-url>/?api=https://<your-backend-url>
```

The backend URL is stored in `localStorage` after the first load, so you can
bookmark the plain URL without the query string.

## What runs where

| Concern | Where it runs |
|---|---|
| Static UI | Vercel (`frontend/public/`) |
| FastAPI + LangGraph + Playwright + Chroma + SQLite | Your backend host (Fly.io / Render / Railway / VM / Docker) |
| Screenshots / annotated images | Served from `/artifacts/…` by the backend |
| LLM calls | Made by the backend only — no keys ever reach the browser |

## Local preview

```bash
cd frontend
npm start            # uses `serve` to host ./public at http://localhost:3000
```

Then: `http://localhost:3000/?api=http://localhost:8000`
