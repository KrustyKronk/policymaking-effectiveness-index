"""Add MANIFEST entries (sha256, bytes, mtime) for raw files that lack one, e.g. after concurrent-write losses.
URL is unknown for rebuilt entries and recorded as such."""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from pipeline.common import MANIFEST, RAW, log


def main():
    entries = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    added = 0
    for f in sorted(RAW.rglob("*")):
        if not f.is_file() or f.name.startswith(".") or f == MANIFEST or f.suffix == ".log":
            continue
        rel = str(f.relative_to(RAW))
        if rel in entries:
            continue
        b = f.read_bytes()
        entries[rel] = {"url": "unknown (entry rebuilt)", "fetched_at": dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc).isoformat(timespec="seconds"),
                        "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
        added += 1
    MANIFEST.write_text(json.dumps(dict(sorted(entries.items())), indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("manifest: %d entries (%d rebuilt)", len(entries), added)


if __name__ == "__main__":
    main()
