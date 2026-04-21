"""Secondary accessibility audit over the raw HTML.

Runs a small set of deterministic, high-signal checks directly on the parsed
DOM. It is intentionally narrow — the purpose is to cross-check the axe-core
findings and produce confidence tags, not to replicate a full audit.

Checks implemented:
  * images without alt text
  * inputs without an associated label
  * empty buttons / links (no accessible name)
  * page missing <title>
  * page missing lang attribute
  * document missing main landmark
  * skipped heading levels (h1 -> h3)

Each returned issue includes a rule_id that is aligned with the axe vocabulary
where reasonable, enabling overlap detection in the orchestration layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore


@dataclass
class SecondaryIssue:
    rule_id: str
    title: str
    severity: str  # critical | serious | moderate | minor
    description: str
    help_text: str
    selector: Optional[str] = None
    html_snippet: Optional[str] = None


def _css_for(el) -> str:
    bits = [el.name]
    if el.get("id"):
        bits.append(f"#{el['id']}")
    cls = el.get("class")
    if cls:
        bits.append("." + ".".join(cls[:2]))
    return "".join(bits)


def audit_html(html: str) -> List[SecondaryIssue]:
    if not html or BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "lxml")
    issues: List[SecondaryIssue] = []

    # images missing alt
    for img in soup.find_all("img"):
        if img.get("role") == "presentation":
            continue
        if img.has_attr("alt"):
            continue
        issues.append(
            SecondaryIssue(
                rule_id="image-alt",
                title="Image is missing alt text",
                severity="serious",
                description="<img> element has no alt attribute.",
                help_text="Add an alt attribute. Use alt='' for purely decorative images.",
                selector=_css_for(img),
                html_snippet=str(img)[:400],
            )
        )

    # inputs without labels
    for inp in soup.find_all(["input", "select", "textarea"]):
        if inp.get("type") in ("hidden", "submit", "button", "image", "reset"):
            continue
        input_id = inp.get("id")
        labelled = False
        if input_id:
            if soup.find("label", attrs={"for": input_id}):
                labelled = True
        if not labelled and inp.find_parent("label"):
            labelled = True
        if not labelled and (inp.get("aria-label") or inp.get("aria-labelledby")):
            labelled = True
        if not labelled and inp.get("title"):
            labelled = True
        if not labelled:
            issues.append(
                SecondaryIssue(
                    rule_id="label",
                    title="Form field has no accessible label",
                    severity="serious",
                    description="Form control lacks an associated <label> or aria-label.",
                    help_text=(
                        "Wrap the field in a <label> or add aria-label / aria-labelledby."
                    ),
                    selector=_css_for(inp),
                    html_snippet=str(inp)[:400],
                )
            )

    # empty buttons / links
    for tag_name, rule, title in (
        ("button", "button-name", "Button has no discernible text"),
        ("a", "link-name", "Link has no discernible text"),
    ):
        for el in soup.find_all(tag_name):
            text = (el.get_text() or "").strip()
            aria = el.get("aria-label") or el.get("aria-labelledby") or el.get("title")
            has_img_alt = any(
                (img.get("alt") or "").strip() for img in el.find_all("img")
            )
            if text or aria or has_img_alt:
                continue
            if tag_name == "a" and not el.get("href"):
                continue
            issues.append(
                SecondaryIssue(
                    rule_id=rule,
                    title=title,
                    severity="serious",
                    description=f"<{tag_name}> has no accessible name.",
                    help_text=(
                        "Add visible text, aria-label, or an image with non-empty alt."
                    ),
                    selector=_css_for(el),
                    html_snippet=str(el)[:400],
                )
            )

    # <title>
    if not soup.find("title") or not (soup.title.string or "").strip():
        issues.append(
            SecondaryIssue(
                rule_id="document-title",
                title="Document has no page title",
                severity="serious",
                description="The <title> element is missing or empty.",
                help_text="Add a concise, descriptive <title> to the document head.",
                selector="head > title",
            )
        )

    # <html lang>
    html_el = soup.find("html")
    if html_el is not None and not html_el.get("lang"):
        issues.append(
            SecondaryIssue(
                rule_id="html-has-lang",
                title="<html> element has no lang attribute",
                severity="serious",
                description="Assistive tech relies on lang to pick the right voice/pronunciation.",
                help_text='Add lang, e.g. <html lang="en">.',
                selector="html",
            )
        )

    # main landmark
    has_main = bool(soup.find("main") or soup.find(attrs={"role": "main"}))
    if not has_main:
        issues.append(
            SecondaryIssue(
                rule_id="landmark-one-main",
                title="Page has no main landmark",
                severity="moderate",
                description="No <main> element or role='main' region was found.",
                help_text="Wrap the primary content in a <main> element.",
                selector="body",
            )
        )

    # heading order (h1 → h3 without h2, etc.)
    last_level = 0
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        level = int(h.name[1])
        if last_level and level > last_level + 1:
            issues.append(
                SecondaryIssue(
                    rule_id="heading-order",
                    title="Heading levels skip",
                    severity="moderate",
                    description=f"Jumped from h{last_level} to h{level}.",
                    help_text="Use sequential heading levels so assistive tech can parse structure.",
                    selector=_css_for(h),
                    html_snippet=str(h)[:200],
                )
            )
        last_level = level

    return issues


def overlap_confidence(axe_rule_ids: List[str], rule_id: str) -> str:
    """Return confidence tag given whether this rule is confirmed by axe."""
    return "high" if rule_id in axe_rule_ids else "medium"
