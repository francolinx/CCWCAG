"""Playwright-based browser crawl + axe-core injection.

Runs each URL through a real headless browser, captures a full-page screenshot,
the rendered HTML, and the list of candidate interactive elements. Also runs
axe-core in the page context and returns its structured results.

The service is defensive:
  * missing Playwright browsers raise a clear error up-front
  * per-page timeouts degrade to an error for that page instead of killing the scan
  * axe-core is loaded from a vendored file if present, else fetched from a CDN
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import get_settings
from ..core.logging import get_logger
from ..utils.paths import screenshots_dir

_log = get_logger(__name__)

_AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.0/axe.min.js"
_AXE_LOCAL = Path(__file__).resolve().parent.parent.parent / "data" / "axe.min.js"


@dataclass
class PageCaptureResult:
    url: str
    final_url: Optional[str] = None
    title: Optional[str] = None
    http_status: Optional[int] = None
    html: Optional[str] = None
    screenshot_path: Optional[str] = None
    interactive_selectors: List[str] = field(default_factory=list)
    axe_results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status: str = "ok"  # ok | error | partial


def _axe_script_source() -> str:
    if _AXE_LOCAL.exists():
        return _AXE_LOCAL.read_text(encoding="utf-8")
    return ""  # fall back to CDN via add_script_tag


class BrowserService:
    """Reusable headless browser that opens one context per scan."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._pw = None
        self._browser = None

    async def __aenter__(self) -> "BrowserService":
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright is not installed. Run `pip install -r requirements.txt` "
                "and `playwright install chromium`."
            ) from e
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self._settings.playwright_headless,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            if self._pw is not None:
                await self._pw.stop()

    async def capture(
        self,
        url: str,
        *,
        scan_id: str,
        page_id: str,
        store_screenshot: bool = True,
    ) -> PageCaptureResult:
        result = PageCaptureResult(url=url)
        assert self._browser is not None, "BrowserService must be used as a context manager"

        timeout_ms = self._settings.playwright_timeout_ms
        nav_wait = self._settings.playwright_nav_wait
        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 AccessibilityRemediationCopilot/1.0 "
                "(+https://example.com/bot)"
            ),
            viewport={"width": 1366, "height": 900},
        )
        page = await context.new_page()
        try:
            try:
                response = await page.goto(url, timeout=timeout_ms, wait_until=nav_wait)
            except Exception as nav_err:
                # Retry once with a more forgiving wait strategy.
                _log.warning("initial nav failed for %s: %s — retrying", url, nav_err)
                response = await page.goto(
                    url, timeout=timeout_ms, wait_until="domcontentloaded"
                )
            result.http_status = response.status if response else None
            try:
                await page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass  # we already have content
            result.final_url = page.url
            try:
                result.title = await page.title()
            except Exception:
                result.title = None

            # Candidate interactive selectors for the crawl planner / overview.
            try:
                result.interactive_selectors = await page.evaluate(
                    """() => {
                        const sels = [];
                        const els = document.querySelectorAll(
                          'a[href], button, input, select, textarea, [role="button"], [role="link"]'
                        );
                        for (const el of Array.from(els).slice(0, 200)) {
                            const id = el.id ? '#' + el.id : '';
                            const cls = el.className && typeof el.className === 'string'
                              ? '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.')
                              : '';
                            sels.push(el.tagName.toLowerCase() + id + cls);
                        }
                        return sels;
                    }"""
                )
            except Exception:
                result.interactive_selectors = []

            # HTML snapshot.
            try:
                result.html = await page.content()
            except Exception:
                result.html = None

            # Screenshot (full page).
            if store_screenshot:
                out = screenshots_dir() / f"{scan_id}_{page_id}.png"
                try:
                    await page.screenshot(path=str(out), full_page=True)
                    result.screenshot_path = str(out)
                except Exception as e:
                    _log.warning("screenshot failed for %s: %s", url, e)

            # Inject axe-core and run.
            result.axe_results = await self._run_axe(page)

        except Exception as e:
            _log.warning("capture error for %s: %s", url, e)
            result.error = str(e)
            result.status = "error" if result.html is None else "partial"
        finally:
            await context.close()
        return result

    async def _run_axe(self, page) -> Optional[Dict[str, Any]]:
        try:
            src = _axe_script_source()
            if src:
                await page.add_script_tag(content=src)
            else:
                await page.add_script_tag(url=_AXE_CDN)
            # Wait up to 5s for axe to be defined.
            await page.wait_for_function("typeof window.axe !== 'undefined'", timeout=5_000)
            raw = await page.evaluate(
                """async () => {
                    try {
                        const res = await window.axe.run(document, {
                            resultTypes: ['violations'],
                        });
                        return res;
                    } catch (e) {
                        return { error: String(e) };
                    }
                }"""
            )
            return raw
        except Exception as e:
            _log.warning("axe injection failed: %s", e)
            return None

    async def get_bbox(
        self, url: str, selector: str, *, timeout_ms: int = 8_000
    ) -> Optional[Dict[str, float]]:
        """Open URL fresh and resolve a bounding box for `selector`."""
        assert self._browser is not None
        context = await self._browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        try:
            try:
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            except Exception:
                return None
            try:
                handle = await page.query_selector(selector)
                if handle is None:
                    return None
                box = await handle.bounding_box()
                return box  # {x, y, width, height}
            except Exception:
                return None
        finally:
            await context.close()
