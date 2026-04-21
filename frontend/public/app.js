// Tiny vanilla JS frontend for the Accessibility Remediation Copilot.
// Points at the same-origin API by default; override with ?api=<url> for
// a frontend deployed elsewhere (e.g. Vercel) talking to a remote backend.

const qs = new URLSearchParams(location.search);
const API = (qs.get("api") || localStorage.getItem("api_base") || "").replace(/\/$/, "");
if (qs.get("api")) localStorage.setItem("api_base", qs.get("api"));

const api = (path) => (API ? API + path : path);

const $ = (id) => document.getElementById(id);

async function getJSON(path) {
  const res = await fetch(api(path), { headers: { "Accept": "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function postJSON(path, body) {
  const res = await fetch(api(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`${res.status} ${t}`);
  }
  return res.json();
}

function setProgress(pct, label) {
  $("progress-card").hidden = false;
  $("progress-bar").style.width = `${Math.max(2, Math.min(100, pct))}%`;
  $("progress-line").textContent = label;
}

function sevClass(sev) { return "finding " + (sev || "minor"); }

function renderFindings(payload, scanOut) {
  const container = $("findings");
  container.innerHTML = "";
  if (!payload.pages || !payload.pages.length) {
    container.innerHTML = '<p class="muted">No pages scanned.</p>';
    return;
  }
  for (const group of payload.pages) {
    const wrap = document.createElement("div");
    wrap.className = "page-group";
    const title = group.page.title || group.page.url;
    wrap.innerHTML = `
      <h3>${escape(title)}</h3>
      <div class="url">${escape(group.page.url)} <span class="muted">· ${group.findings.length} findings</span></div>
      ${group.page.screenshot_url ? `<details><summary>View page screenshot</summary>
        <img src="${api(group.page.screenshot_url)}" alt="Screenshot of ${escape(title)}" style="margin-top:10px;max-width:100%;border-radius:8px;" />
      </details>` : ""}
    `;
    if (!group.findings.length) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "No findings on this page 🎉";
      wrap.appendChild(p);
    }
    for (const f of group.findings) {
      const el = document.createElement("div");
      el.className = sevClass(f.severity);
      const refs = (f.wcag_refs || []).map(r =>
        r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${escape(r.criterion)}</a>` : escape(r.criterion)
      ).join(" · ");
      const rem = f.remediation || {};
      el.innerHTML = `
        <h4>${escape(f.title)}</h4>
        <div class="meta">
          <span>${escape(f.severity)}</span>
          <span>${escape(f.source)}</span>
          <span>confidence: ${escape(f.confidence)}</span>
          ${f.selector ? `<span><code>${escape(f.selector)}</code></span>` : ""}
        </div>
        ${rem.explanation ? `<p>${escape(rem.explanation)}</p>` : ""}
        ${rem.why_it_matters ? `<p><strong>Why it matters:</strong> ${escape(rem.why_it_matters)}</p>` : ""}
        ${rem.how_to_fix ? `<p><strong>How to fix:</strong> ${escape(rem.how_to_fix)}</p>` : ""}
        ${rem.code_snippet ? `<pre><code>${escape(rem.code_snippet)}</code></pre>` : ""}
        ${f.annotated_screenshot_url ? `<img class="annotated" src="${api(f.annotated_screenshot_url)}" alt="Annotated screenshot of the issue" />` : ""}
        ${refs ? `<div class="ref">WCAG: ${refs}</div>` : `<div class="ref">WCAG: (ungrounded — human review recommended)</div>`}
      `;
      wrap.appendChild(el);
    }
    container.appendChild(wrap);
  }
}

function renderHeader(scan) {
  $("result-card").hidden = false;
  $("result-title").textContent = `${scan.domain} — ${scan.status}`;
  $("result-exec").textContent = scan.executive_summary || "";
  $("score").textContent = scan.score != null ? scan.score : "–";
  $("grade").textContent = scan.grade || "";

  const s = (scan.stats && scan.stats.severity_breakdown) || {};
  const bar = $("severity-bar");
  bar.innerHTML = "";
  for (const k of ["critical", "serious", "moderate", "minor"]) {
    const n = s[k] || 0;
    if (n === 0) continue;
    const span = document.createElement("span");
    span.className = `sv-${k}`;
    span.textContent = `${n} ${k}`;
    bar.appendChild(span);
  }
}

async function pollScan(id) {
  setProgress(5, "Planning crawl…");
  let tick = 0;
  while (true) {
    tick += 1;
    const scan = await getJSON(`/api/scans/${id}`);
    const st = scan.status;
    if (st === "succeeded" || st === "failed" || st === "partial") {
      setProgress(100, st);
      return scan;
    }
    const phases = [
      "Planning crawl…",
      "Rendering pages with Playwright…",
      "Running axe-core…",
      "Secondary audit…",
      "Retrieving WCAG evidence…",
      "Generating annotated screenshots…",
      "Producing remediation snippets…",
      "Synthesizing report…",
    ];
    const label = phases[Math.min(tick - 1, phases.length - 1)];
    setProgress(Math.min(95, 10 + tick * 10), label);
    await new Promise(r => setTimeout(r, 2500));
  }
}

async function loadHistory(scan) {
  try {
    const prior = await getJSON(`/api/scans/${scan.id}/history`);
    if (!prior.length) { $("history-card").hidden = true; return; }
    $("history-card").hidden = false;
    const ul = $("history-list");
    ul.innerHTML = "";
    for (const p of prior.slice(0, 10)) {
      const li = document.createElement("li");
      li.innerHTML = `
        <span>${new Date(p.created_at).toLocaleString()} · score ${p.score ?? "–"} · ${p.findings_count} findings</span>
        <button data-id="${p.id}">Compare</button>
      `;
      li.querySelector("button").addEventListener("click", async () => {
        const cmp = await getJSON(`/api/scans/${scan.id}/compare/${p.id}`);
        $("compare-result").innerHTML = `
          <p class="muted">Δ vs ${new Date(p.created_at).toLocaleString()}:
            <strong>${cmp.delta.new}</strong> new ·
            <strong>${cmp.delta.resolved}</strong> resolved ·
            <strong>${cmp.delta.recurring}</strong> recurring
            ${cmp.score_delta != null ? `· score Δ ${cmp.score_delta > 0 ? "+" : ""}${cmp.score_delta}` : ""}
          </p>
        `;
      });
      ul.appendChild(li);
    }
  } catch (e) { /* no-op */ }
}

async function runScan() {
  const root_url = $("url").value.trim();
  const payload = {
    root_url,
    crawl_depth: parseInt($("depth").value, 10),
    page_limit: parseInt($("limit").value, 10),
    use_secondary: $("secondary").checked,
    store_screenshots: $("screenshots").checked,
    strict_mode: false,
  };
  const scan = await postJSON("/api/scans", payload);
  const done = await pollScan(scan.id);
  renderHeader(done);
  const findings = await getJSON(`/api/scans/${done.id}/findings`);
  renderFindings(findings, done);
  loadHistory(done);
}

function escape(s) {
  return (s == null ? "" : String(s))
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

async function init() {
  try {
    const cfg = await getJSON("/api/config");
    $("config-line").textContent =
      `Backend: ${cfg.app_env} · model: ${cfg.model_name} · LLM ${cfg.llm_enabled ? "on" : "off (deterministic fallback)"} · embeddings: ${cfg.embeddings_provider}`;
  } catch (e) {
    $("config-line").textContent = `Backend not reachable at ${API || location.origin}. Pass ?api=<url> to point at a remote backend.`;
  }
  $("scan-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    $("result-card").hidden = true;
    $("history-card").hidden = true;
    try { await runScan(); }
    catch (e) { setProgress(100, `Failed: ${e.message}`); }
  });
}
init();
