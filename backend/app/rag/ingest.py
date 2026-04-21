"""Ingest the WCAG corpus into Chroma (with a NumPy-backed fallback).

Chunks each corpus file by Markdown section, embeds each chunk, and stores
the result along with metadata (criterion, level, URL). Re-running is
idempotent — the collection is dropped and rebuilt.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..core.config import get_settings
from ..core.logging import get_logger
from .embeddings import EmbeddingsProvider

_log = get_logger(__name__)

_COLLECTION = "wcag_corpus"


@dataclass
class Chunk:
    id: str
    text: str
    metadata: Dict[str, Any]


def _parse_header(path: Path) -> Dict[str, Any]:
    """Extract criterion info from the first heading line, e.g. `# 1.1.1 ...`."""
    with path.open(encoding="utf-8") as fh:
        first = fh.readline().strip()
    m = re.match(r"#\s+([\d.]+)\s+(.+?)(?:\s+\((Level\s+[A-Z]+)\))?$", first)
    crit_num = None
    crit_title = None
    level = None
    if m:
        crit_num = m.group(1)
        crit_title = m.group(2).strip()
        level = (m.group(3) or "").replace("Level", "").strip() or None
    # Canonical URL inside the file?
    url = None
    text = path.read_text(encoding="utf-8")
    m2 = re.search(r"Canonical URL:\s+(\S+)", text)
    if m2:
        url = m2.group(1)
    return {
        "file": path.name,
        "criterion_number": crit_num,
        "criterion_title": crit_title,
        "criterion": f"{crit_num} {crit_title}" if crit_num else path.stem,
        "level": level,
        "url": url,
    }


def _chunk_markdown(text: str, *, max_chars: int = 900) -> List[str]:
    """Split on H2 boundaries, then window long chunks."""
    parts = re.split(r"\n(?=##\s)", text)
    chunks: List[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chars:
            chunks.append(part)
            continue
        # Window long sections by paragraphs.
        buf = ""
        for para in re.split(r"\n{2,}", part):
            if len(buf) + len(para) + 2 <= max_chars:
                buf = f"{buf}\n\n{para}" if buf else para
            else:
                if buf:
                    chunks.append(buf.strip())
                buf = para
        if buf:
            chunks.append(buf.strip())
    return chunks


def _discover_corpus(root: Path) -> List[Path]:
    return sorted(p for p in root.glob("*.md") if p.name != "SOURCES.md")


def build_chunks(root: Optional[Path] = None) -> List[Chunk]:
    s = get_settings()
    root = root or Path(s.wcag_corpus_dir)
    chunks: List[Chunk] = []
    for path in _discover_corpus(root):
        meta = _parse_header(path)
        text = path.read_text(encoding="utf-8")
        for i, piece in enumerate(_chunk_markdown(text)):
            chunks.append(
                Chunk(
                    id=f"{path.stem}#{i}",
                    text=piece,
                    metadata={**meta, "chunk_index": i},
                )
            )
    return chunks


# ---------------- Chroma-backed store ----------------

def _use_chroma() -> bool:
    try:
        import chromadb  # noqa: F401

        return True
    except Exception:
        return False


def _chroma_client():
    import chromadb

    s = get_settings()
    Path(s.vector_db_path).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=s.vector_db_path)


def ingest() -> Dict[str, Any]:
    emb = EmbeddingsProvider()
    chunks = build_chunks()
    if not chunks:
        return {"chunks": 0, "backend": "none", "embedding": emb.kind}

    texts = [c.text for c in chunks]
    vectors = emb.embed(texts)

    if _use_chroma():
        client = _chroma_client()
        try:
            client.delete_collection(_COLLECTION)
        except Exception:
            pass
        col = client.get_or_create_collection(
            name=_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        col.add(
            ids=[c.id for c in chunks],
            documents=texts,
            embeddings=vectors,
            metadatas=[c.metadata for c in chunks],
        )
        _log.info("ingested %d chunks into chroma (%s)", len(chunks), emb.kind)
        return {"chunks": len(chunks), "backend": "chroma", "embedding": emb.kind}

    # NumPy fallback: dump to a flat JSON file.
    out = Path(get_settings().vector_db_path) / "flat_store.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dim": emb.dimension,
        "embedding": emb.kind,
        "items": [
            {"id": c.id, "text": c.text, "metadata": c.metadata, "vector": v}
            for c, v in zip(chunks, vectors)
        ],
    }
    out.write_text(json.dumps(payload), encoding="utf-8")
    _log.info("ingested %d chunks into flat store (%s)", len(chunks), emb.kind)
    return {"chunks": len(chunks), "backend": "flat", "embedding": emb.kind}


if __name__ == "__main__":
    print(json.dumps(ingest(), indent=2))
