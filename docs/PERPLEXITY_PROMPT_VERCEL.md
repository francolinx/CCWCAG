# Perplexity prompt — Vercel frontend deploy

> Paste everything between the `===` lines into Perplexity (or Perplexity
> Comet / Copilot). It gives Perplexity enough context to walk you through
> the current Vercel dashboard UI step-by-step.

===

I need you to walk me, step by step, through deploying the **static
frontend** of a GitHub repo to **Vercel** using the current (2025/2026)
Vercel dashboard. I want exact click paths, menu names as they appear
today, and the exact values to enter in each field. Assume I am logged
into Vercel with a Hobby account and have already connected my GitHub
account.

## Repo details
- GitHub repo: `https://github.com/francolinx/CCWCAG`
- Branch to deploy: `claude/build-accessibility-remedia-6sVZ8`
- Project type: **pure static site** — plain HTML/CSS/JS, no framework,
  no build step.
- At the **repo root** there is already a `vercel.json` with:
  ```json
  {
    "version": 2,
    "buildCommand": null,
    "installCommand": null,
    "outputDirectory": "frontend/public",
    "cleanUrls": true,
    "trailingSlash": false
  }
  ```
- The files to serve live at `frontend/public/` (index.html, style.css,
  app.js, favicon.svg).
- There is also a `frontend/` subfolder with its own `vercel.json` and
  `package.json` in case Vercel's "Root Directory" pattern works better
  than a root-level config.

## What the frontend does
It is a single-page UI that talks to a **separate FastAPI backend**
hosted on Render. The backend URL must be injected into the frontend at
runtime via the `?api=` query parameter (the frontend caches it in
`localStorage`). My backend URL will look like
`https://accessibility-remediation-copilot-api-XXXX.onrender.com`.

## What I need from you
1. Tell me whether to use **"Add New → Project → Import Git Repository"**
   from the dashboard, and walk me through the exact current screens —
   which buttons, what the field labels say today, what to select in the
   **Framework Preset** dropdown (should be "Other" / "No Framework"),
   and whether to set the **Root Directory** to `.` (with the root
   `vercel.json`) or to `frontend/` (with the inner one). Recommend one
   path and explain why.
2. Tell me exactly what to put in:
   - Build Command
   - Output Directory
   - Install Command
   - Node version
   …given that this is a static site with no build step.
3. Explain how to set the **Production Branch** to
   `claude/build-accessibility-remedia-6sVZ8` instead of `main`, in the
   current dashboard UI.
4. After the first deploy succeeds, tell me how to:
   - Find the production URL.
   - Open it with the `?api=https://<my-render-url>` query string so the
     frontend pairs with my Render backend, and confirm it caches to
     `localStorage`.
   - Add a **custom domain** later (optional, just point me at the right
     tab).
5. Call out anything that commonly trips people up on a static-only
   Vercel deploy in the current UI (e.g., auto-detected framework
   preset overriding `vercel.json`, SPA rewrites, the "Ignored Build
   Step" field, protection settings on Hobby).
6. Give me a short **verification checklist** at the end: how to confirm
   `index.html`, `style.css`, and `app.js` are all being served with the
   right MIME types and that `cleanUrls: true` is taking effect.

Please cite the current Vercel docs pages you rely on and prefer
up-to-date sources over blog posts older than 2024. Keep the tone
concrete and copy-paste friendly — no generic "go to settings" hand
waves.

===
