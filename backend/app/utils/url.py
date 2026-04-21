"""URL helpers — domain extraction, normalization, on-domain filtering."""
from __future__ import annotations

from typing import Iterable, List, Optional, Set
from urllib.parse import urldefrag, urljoin, urlparse


def canonical_domain(url: str) -> str:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def same_site(a: str, b: str) -> bool:
    return canonical_domain(a) == canonical_domain(b) and canonical_domain(a) != ""


def normalize_url(base: str, href: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    try:
        joined = urljoin(base, href)
    except Exception:
        return None
    joined, _ = urldefrag(joined)
    p = urlparse(joined)
    if p.scheme not in ("http", "https"):
        return None
    # Drop default ports and trailing slashes for consistency.
    netloc = p.netloc.lower()
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return f"{p.scheme}://{netloc}{path}{('?' + p.query) if p.query else ''}"


def dedupe_preserving_order(urls: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


IMPORTANT_KEYWORDS = (
    "cart",
    "checkout",
    "product",
    "shop",
    "collection",
    "collections",
    "catalog",
    "catalogue",
    "category",
    "categories",
    "search",
    "account",
    "login",
    "sign-in",
    "signup",
    "register",
    "contact",
    "about",
    "help",
    "support",
    "faq",
    "menu",
    "nav",
)


def score_candidate(url: str) -> int:
    """Heuristic priority score for crawl planning. Higher = more important."""
    u = url.lower()
    score = 0
    path = urlparse(u).path or "/"
    if path in ("", "/"):
        score += 100
    for kw in IMPORTANT_KEYWORDS:
        if kw in u:
            score += 20
    # Penalize very deep paths.
    depth = path.count("/")
    if depth > 4:
        score -= 5 * (depth - 4)
    return score
