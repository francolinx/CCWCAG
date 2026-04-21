"""Application configuration.

Loaded from environment (.env). All secrets stay on the server — the public
`/api/config` endpoint exposes only non-sensitive fields.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM ---
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # --- Embeddings ---
    embeddings_provider: str = "local"  # "local" | "openai"
    embeddings_model: str = "all-MiniLM-L6-v2"

    # --- Browser ---
    playwright_headless: bool = True
    playwright_timeout_ms: int = 30_000
    playwright_nav_wait: str = "networkidle"

    # --- Storage ---
    sqlite_path: str = "./backend/data/app.db"
    vector_db_path: str = "./backend/data/vectorstore"
    artifacts_dir: str = "./backend/data/artifacts"
    wcag_corpus_dir: str = "./backend/data/wcag_corpus"

    # --- Server ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "dev"
    cors_allow_origins: str = "*"

    # --- Scan defaults ---
    default_crawl_depth: int = 1
    default_page_limit: int = 5
    default_use_secondary: bool = True
    default_store_screenshots: bool = True
    default_strict_mode: bool = False

    @field_validator("cors_allow_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip() or "*"

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_allow_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def sqlite_url(self) -> str:
        path = Path(self.sqlite_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path}"

    @property
    def sqlite_sync_url(self) -> str:
        path = Path(self.sqlite_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"

    def ensure_dirs(self) -> None:
        for p in (
            self.artifacts_dir,
            self.vector_db_path,
            self.wcag_corpus_dir,
            str(Path(self.artifacts_dir) / "screenshots"),
            str(Path(self.artifacts_dir) / "annotations"),
            str(Path(self.artifacts_dir) / "reports"),
        ):
            Path(p).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
