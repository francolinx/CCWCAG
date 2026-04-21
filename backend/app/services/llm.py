"""OpenAI-compatible LLM client with a deterministic fallback.

When `OPENAI_API_KEY` is configured the real model is used. Otherwise the
`deterministic_fallback` function returns a rule-based remediation that is
grounded in retrieved WCAG evidence. The whole app therefore stays demo-
runnable with zero secrets — while being just a flag-flip away from live LLM
reasoning.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import get_settings
from ..core.logging import get_logger

_log = get_logger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None
        if self._settings.llm_enabled:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self._settings.openai_api_key,
                    base_url=self._settings.openai_base_url,
                )
                _log.info("LLM client ready (%s)", self._settings.model_name)
            except Exception as e:  # pragma: no cover
                _log.warning("LLM client init failed: %s", e)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    def json_complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> Optional[Dict[str, Any]]:
        """Ask the model for a JSON object. Returns None on total failure."""
        if not self.enabled:
            return None
        try:
            resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                model=self._settings.model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            content = resp.choices[0].message.content or "{}"
            return _safe_json(content)
        except Exception as e:
            _log.warning("LLM call failed: %s", e)
            return None

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    def text_complete(
        self, *, system: str, user: str, temperature: float = 0.3, max_tokens: int = 500
    ) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                model=self._settings.model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            _log.warning("LLM call failed: %s", e)
            return None


def _safe_json(s: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON parse. LLMs occasionally wrap output in code fences."""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        # Try to rescue the first JSON object.
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


_singleton: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _singleton
    if _singleton is None:
        _singleton = LLMClient()
    return _singleton
