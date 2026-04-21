"""SQLAlchemy ORM models.

A single-file module keeps the schema easy to reason about for an MVP.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    root_url: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # pending | running | succeeded | failed | partial
    crawl_depth: Mapped[int] = mapped_column(Integer, default=1)
    page_limit: Mapped[int] = mapped_column(Integer, default=5)
    use_secondary: Mapped[bool] = mapped_column(default=True)
    store_screenshots: Mapped[bool] = mapped_column(default=True)
    strict_mode: Mapped[bool] = mapped_column(default=False)

    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    summary_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stats_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    pages: Mapped[list["Page"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    url: Mapped[str] = mapped_column(String(1024))
    final_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    html_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    scan: Mapped[Scan] = relationship(back_populates="pages")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("scan_id", "page_id", "rule_id", "selector", name="uq_finding"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    help_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    help_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), default="minor", index=True)
    # critical | serious | moderate | minor
    source: Mapped[str] = mapped_column(String(32), default="axe")
    # axe | secondary | heuristic
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    selector: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    html_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bbox_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    annotated_screenshot_path: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )
    wcag_refs_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    remediation_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    scan: Mapped[Scan] = relationship(back_populates="findings")
    page: Mapped[Page] = relationship(back_populates="findings")


class ScanComparison(Base):
    __tablename__ = "scan_comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    previous_scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
