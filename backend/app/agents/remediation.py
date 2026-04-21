"""Remediation Agent.

For each finding, produces:
  * plain-English explanation
  * why it matters
  * exact fix recommendation
  * code snippet
  * implementation notes
  * `grounded` flag based on whether WCAG evidence was available

If the LLM is configured, uses it with a tight JSON-only prompt that references
retrieved WCAG chunks. Otherwise, falls back to a rule-based template that
still leverages the retrieved evidence for the "why it matters" and citation
sections — so the output is never fabricated.

To keep costs and latency reasonable we cache per rule_id: once we've produced
a remediation for `image-alt`, we reuse it across all `image-alt` findings and
only swap in the page-specific selector / snippet.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger
from ..services.llm import get_llm
from .prompts import REMEDIATION_SYSTEM
from .state import RawFinding, ScanState

_log = get_logger(__name__)


# Minimal rule → snippet knowledge used by the deterministic fallback. These
# are intentionally short, canonical examples aligned with WCAG guidance.
_FALLBACK_SNIPPETS: Dict[str, Dict[str, str]] = {
    "image-alt": {
        "how_to_fix": "Add a descriptive alt attribute to every <img>. Use alt=\"\" for purely decorative images.",
        "snippet": '<!-- meaningful image -->\n<img src="product.jpg" alt="Red leather backpack, front view">\n\n<!-- decorative image -->\n<img src="divider.svg" alt="" role="presentation">',
    },
    "label": {
        "how_to_fix": "Associate every form control with a <label for> or an aria-label.",
        "snippet": '<label for="email">Email address</label>\n<input id="email" type="email" name="email" autocomplete="email" required>',
    },
    "button-name": {
        "how_to_fix": "Give every button an accessible name via visible text, aria-label, or an image alt.",
        "snippet": '<!-- visible text is best -->\n<button type="button">Add to cart</button>\n\n<!-- icon-only button needs aria-label -->\n<button type="button" aria-label="Close dialog"><svg aria-hidden="true" ...></svg></button>',
    },
    "link-name": {
        "how_to_fix": "Give every <a> meaningful text (not 'click here'). For icon-only links, add aria-label.",
        "snippet": '<a href="/report.pdf">Download the 2024 report (PDF, 1.2MB)</a>\n<a href="/cart" aria-label="Shopping cart"><svg aria-hidden="true" ...></svg></a>',
    },
    "document-title": {
        "how_to_fix": "Add a concise, unique <title> for every page.",
        "snippet": "<head>\n  <title>Red leather backpack — Acme Store</title>\n</head>",
    },
    "html-has-lang": {
        "how_to_fix": "Set the lang attribute on the <html> element.",
        "snippet": '<html lang="en">',
    },
    "color-contrast": {
        "how_to_fix": "Increase contrast to ≥ 4.5:1 (≥ 3:1 for large text).",
        "snippet": "/* before: #999 on #fff ≈ 2.8:1 */\n.small-text { color: #4a4a4a; } /* ≈ 9:1 on #fff */",
    },
    "landmark-one-main": {
        "how_to_fix": "Wrap the primary content in a <main> element (one per page).",
        "snippet": "<body>\n  <header>...</header>\n  <main>\n    <!-- primary content -->\n  </main>\n  <footer>...</footer>\n</body>",
    },
    "heading-order": {
        "how_to_fix": "Use heading levels sequentially (h1 → h2 → h3). Don't skip.",
        "snippet": "<h1>Page title</h1>\n<h2>Section</h2>\n<h3>Sub-section</h3>",
    },
    "target-size": {
        "how_to_fix": "Ensure tap / click targets are at least 24×24 CSS px (44×44 preferred).",
        "snippet": ".icon-btn { min-width: 44px; min-height: 44px; padding: 10px; }",
    },
    "focus-visible": {
        "how_to_fix": "Don't remove focus outlines without replacement. Use :focus-visible for a clear ring.",
        "snippet": "button:focus-visible,\na:focus-visible {\n  outline: 2px solid #2563eb;\n  outline-offset: 2px;\n}",
    },
}


def _wcag_refs_block(refs: List[Dict[str, Any]]) -> str:
    if not refs:
        return "No grounded WCAG evidence was available. Flag this finding for human review."
    lines = []
    for r in refs[:3]:
        lines.append(f"- {r.get('criterion')} ({r.get('level') or 'Level ?'}) {r.get('url','')}")
        if r.get("snippet"):
            lines.append(f"  > {r['snippet'][:400]}")
    return "\n".join(lines)


def _fallback_remediation(f: RawFinding) -> Dict[str, Any]:
    rule_id = f.get("rule_id") or "unknown"
    refs = f.get("wcag_refs") or []
    tpl = _FALLBACK_SNIPPETS.get(rule_id)
    if tpl:
        how = tpl["how_to_fix"]
        snippet = tpl["snippet"]
    else:
        how = f.get("help_text") or "Review the element against the referenced WCAG success criterion."
        snippet = f.get("html_snippet") or ""

    first_ref = refs[0] if refs else None
    why = (
        f"Users relying on assistive tech may fail to complete tasks on this page. "
        f"This issue maps to {first_ref['criterion']} ({first_ref.get('level') or 'Level ?'})."
        if first_ref
        else "Users relying on assistive tech may be blocked from completing tasks on this page."
    )
    return {
        "explanation": (
            f"Finding: {f.get('title')}. Affects: {f.get('selector') or 'element'}. "
            f"{(f.get('description') or '').strip()}"
        ),
        "why_it_matters": why,
        "how_to_fix": how,
        "code_snippet": snippet,
        "implementation_notes": (
            "Verify on the exact element in context; related instances on other "
            "pages may need the same fix."
        ),
        "grounded": bool(refs),
    }


def _llm_remediation(f: RawFinding) -> Optional[Dict[str, Any]]:
    llm = get_llm()
    if not llm.enabled:
        return None
    payload = {
        "finding": {
            "rule_id": f.get("rule_id"),
            "title": f.get("title"),
            "description": f.get("description"),
            "severity": f.get("severity"),
            "selector": f.get("selector"),
            "html_snippet": (f.get("html_snippet") or "")[:1500],
            "page_url": f.get("page_url"),
        },
        "wcag_evidence": f.get("wcag_refs") or [],
    }
    obj = llm.json_complete(
        system=REMEDIATION_SYSTEM,
        user=json.dumps(payload),
        temperature=0.2,
        max_tokens=700,
    )
    if not obj:
        return None
    required = ("explanation", "why_it_matters", "how_to_fix")
    if not all(k in obj for k in required):
        return None
    obj.setdefault("code_snippet", "")
    obj.setdefault("implementation_notes", "")
    obj["grounded"] = bool(f.get("wcag_refs"))
    return obj


async def generate_remediations(state: ScanState) -> ScanState:
    findings: List[RawFinding] = state.get("findings") or []
    cache: Dict[str, Dict[str, Any]] = {}

    for f in findings:
        rule_id = f.get("rule_id") or "unknown"
        if rule_id in cache:
            rem = dict(cache[rule_id])
        else:
            rem = _llm_remediation(f) or _fallback_remediation(f)
            cache[rule_id] = rem
        # Per-finding touch-up: make explanation reference this selector.
        if f.get("selector") and rem.get("explanation"):
            rem = dict(rem)
            rem["explanation"] = (
                rem["explanation"].rstrip(".") + f". Element: `{f['selector']}`."
            )
        f["remediation"] = rem

    _log.info("remediation generated for %d findings (cache size %d)", len(findings), len(cache))
    return state
