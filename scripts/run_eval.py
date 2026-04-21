"""Lightweight evaluation harness.

Runs the end-to-end scan flow against two targets:
  * a known-good demo site,
  * a known-bad demo site (intentionally full of a11y defects).

Aggregates:
  * pages scanned
  * findings count
  * severity breakdown
  * % with screenshot evidence
  * % with WCAG evidence
  * scan comparison functionality status (runs a 2nd scan of the "bad" site
    to exercise /compare)

Writes the final JSON to backend/data/artifacts/reports/eval_<timestamp>.json
and prints a human-readable summary.

Default targets are innocuous public demos; override with --url-good /
--url-bad.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import httpx  # noqa: E402

from backend.app.core.config import get_settings  # noqa: E402


async def _start_and_wait(client: httpx.AsyncClient, url: str, page_limit: int = 3) -> Dict[str, Any]:
    r = await client.post(
        "/api/scans",
        json={"root_url": url, "crawl_depth": 1, "page_limit": page_limit},
        timeout=30,
    )
    r.raise_for_status()
    scan_id = r.json()["id"]
    for _ in range(60):
        s = (await client.get(f"/api/scans/{scan_id}")).json()
        if s["status"] in ("succeeded", "failed", "partial"):
            return s
        await asyncio.sleep(3)
    return {"id": scan_id, "status": "timeout"}


async def run(base: str, good: str, bad: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"generated_at": datetime.utcnow().isoformat() + "Z", "targets": {}}
    async with httpx.AsyncClient(base_url=base, timeout=60) as client:
        cfg = (await client.get("/api/config")).json()
        out["config"] = cfg

        for label, url in (("good", good), ("bad_first", bad), ("bad_second", bad)):
            t0 = time.time()
            summary = await _start_and_wait(client, url)
            elapsed = round(time.time() - t0, 1)
            detail: Dict[str, Any] = {"url": url, "elapsed_s": elapsed}
            if summary.get("status") in ("succeeded", "partial"):
                findings = (await client.get(f"/api/scans/{summary['id']}/findings")).json()
                total = sum(len(p["findings"]) for p in findings["pages"])
                with_shot = sum(
                    1
                    for p in findings["pages"]
                    for f in p["findings"]
                    if f.get("annotated_screenshot_url")
                )
                with_wcag = sum(
                    1
                    for p in findings["pages"]
                    for f in p["findings"]
                    if f.get("wcag_refs")
                )
                sev: Dict[str, int] = {}
                for p in findings["pages"]:
                    for f in p["findings"]:
                        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
                detail.update(
                    scan_id=summary["id"],
                    status=summary["status"],
                    score=summary.get("score"),
                    grade=summary.get("grade"),
                    pages_scanned=len(findings["pages"]),
                    findings_total=total,
                    severity_breakdown=sev,
                    pct_with_screenshot_evidence=round(100 * with_shot / total, 1) if total else 0,
                    pct_with_wcag_evidence=round(100 * with_wcag / total, 1) if total else 0,
                )
            else:
                detail.update(status=summary.get("status"), error=summary.get("error"))
            out["targets"][label] = detail

        # Exercise compare using the two bad scans.
        try:
            first = out["targets"]["bad_first"].get("scan_id")
            second = out["targets"]["bad_second"].get("scan_id")
            if first and second:
                cmp = (await client.get(f"/api/scans/{second}/compare/{first}")).json()
                out["compare_smoke"] = {
                    "ok": True,
                    "delta": cmp.get("delta"),
                    "score_delta": cmp.get("score_delta"),
                }
            else:
                out["compare_smoke"] = {"ok": False, "reason": "missing bad scans"}
        except Exception as e:
            out["compare_smoke"] = {"ok": False, "error": str(e)}

    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument(
        "--url-good",
        default="https://www.w3.org/WAI/demos/bad/after/home.html",
        help="A well-formed accessibility demo page.",
    )
    parser.add_argument(
        "--url-bad",
        default="https://www.w3.org/WAI/demos/bad/before/home.html",
        help="The BAD version of the same demo (intentional failures).",
    )
    args = parser.parse_args()

    report = asyncio.run(run(args.base, args.url_good, args.url_bad))

    out_dir = Path(get_settings().artifacts_dir) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eval_{int(time.time())}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"eval written to {out_path}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
