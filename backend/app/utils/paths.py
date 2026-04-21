"""Path helpers for screenshots/annotations relative to the artifacts dir."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.config import get_settings


def artifacts_root() -> Path:
    return Path(get_settings().artifacts_dir).resolve()


def screenshots_dir() -> Path:
    p = artifacts_root() / "screenshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def annotations_dir() -> Path:
    p = artifacts_root() / "annotations"
    p.mkdir(parents=True, exist_ok=True)
    return p


def reports_dir() -> Path:
    p = artifacts_root() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def to_public_url(path: Optional[str]) -> Optional[str]:
    """Turn an on-disk artifact path into a URL path under /artifacts/."""
    if not path:
        return None
    p = Path(path)
    try:
        rel = p.resolve().relative_to(artifacts_root())
    except Exception:
        return None
    return "/artifacts/" + str(rel).replace("\\", "/")
