"""Capture HTML / screenshot evidence when something fails.

A failure snapshot is a directory with:
  - dump.html (the page body or a string the caller passes)
  - screenshot.png (only when a Playwright Page is available)
  - context.json (caller-supplied metadata: error, stack, offer_id, etc.)

Snapshots live under <storage_dir>/failures/<timestamp>/ — same parent that
holds state.db so they ride the Railway volume.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def snapshot_dir(base: Path) -> Path:
    return Path(base).expanduser() / "failures"


async def capture_failure(
    *,
    base: Path | str,
    label: str,
    page=None,
    html: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> Path:
    """Persist a failure snapshot. Returns the directory created.

    Robust to missing inputs: anything that fails is logged and skipped, the
    directory itself is always created so the caller can tell the snapshot ran.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = snapshot_dir(Path(base)) / f"{ts}_{label}"
    out.mkdir(parents=True, exist_ok=True)

    if context is None:
        context = {}
    context.setdefault("captured_at", datetime.now().isoformat())
    context.setdefault("label", label)

    # Save context first so we have something even if other captures fail
    try:
        (out / "context.json").write_text(
            json.dumps(context, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning(f"snapshot: failed to write context.json: {exc}")

    # If caller passed raw HTML string, save it directly
    if html is not None:
        try:
            (out / "dump.html").write_text(html, encoding="utf-8")
        except Exception as exc:
            logger.warning(f"snapshot: failed to write dump.html (string): {exc}")

    # If caller passed a Playwright page, capture both screenshot and content
    if page is not None:
        try:
            await page.screenshot(path=str(out / "screenshot.png"), full_page=True)
        except Exception as exc:
            logger.warning(f"snapshot: failed to capture screenshot: {exc}")
        try:
            content = await page.content()
            (out / "dump.html").write_text(content, encoding="utf-8")
        except Exception as exc:
            logger.warning(f"snapshot: failed to capture page content: {exc}")

    logger.info(f"snapshot: captured at {out}")
    return out
