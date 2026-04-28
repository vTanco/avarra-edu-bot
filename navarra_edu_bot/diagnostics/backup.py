"""Daily SQLite backup.

Generates a gzipped copy of the DB and either uploads it to Telegram (as a
document attached to the configured chat) or, when telegram is unavailable,
keeps a rolling local copy under <storage_dir>/backups/.
"""
from __future__ import annotations

import gzip
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_KEEP = 7  # rolling local backups to keep


def _backups_dir(storage_path: Path) -> Path:
    return Path(storage_path).expanduser().parent / "backups"


def _make_local_copy(storage_path: Path) -> Path:
    """Snapshot the DB into <storage_dir>/backups/state-YYYYMMDD.db.gz.

    Returns the path to the gzipped backup. Caller can then upload, prune, etc.
    """
    src = Path(storage_path).expanduser()
    dest_dir = _backups_dir(src)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    dest = dest_dir / f"state-{stamp}.db.gz"

    with src.open("rb") as fin, gzip.open(dest, "wb") as fout:
        shutil.copyfileobj(fin, fout)

    # Prune older backups
    backups = sorted(dest_dir.glob("state-*.db.gz"))
    for old in backups[:-_KEEP]:
        try:
            old.unlink()
        except Exception:
            pass

    return dest


async def daily_backup(
    *,
    storage_path: Path | str,
    bot=None,
    chat_id: Optional[int] = None,
) -> Optional[Path]:
    """Run a daily backup and optionally push it to Telegram.

    Returns the local backup path (always created) or None on hard failure.
    The Telegram upload is best-effort; failures are logged, not raised.
    """
    try:
        backup_path = _make_local_copy(Path(storage_path))
        logger.info(f"backup: created {backup_path}")
    except Exception as exc:
        logger.error(f"backup: local copy failed: {exc}")
        return None

    if bot is not None and chat_id is not None:
        try:
            with backup_path.open("rb") as f:
                await bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=backup_path.name,
                    caption=f"📦 Backup {backup_path.name}",
                )
        except Exception as exc:
            logger.warning(f"backup: telegram upload failed: {exc}")

    return backup_path
