"""Rebuild the WCAG vector store from the markdown corpus.

Usage:
    python scripts/ingest_wcag.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backend.app.rag.ingest import ingest  # noqa: E402


def main() -> None:
    out = ingest()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
