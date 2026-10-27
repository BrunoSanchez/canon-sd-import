#!/usr/bin/env python3
"""Safely copy Canon photos/videos from an SD card to an HDD, one folder per day.

Features:
- Copy to YYYY-MM-DD folders based on source file modification time
- Atomic write via temporary .part file + rename
- fsync file and directory metadata (best effort on non-Windows)
- SHA-256 verification of copied bytes
- Resume-safe: skips files already present with matching hash
- Never deletes from source
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import shutil
import sys
from pathlib import Path

EXTS = {".cr2", ".cr3", ".crw", ".jpg", ".jpeg", ".mp4", ".mov", ".thm", ".xmp", ".heic", ".hif"}
CHUNK = 4 * 1024 * 1024


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def day_folder(src: Path) -> str:
    return dt.datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y-%m-%d")


def fsync_dir(d: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_copy(src: Path, dst: Path) -> str:
    """Copy src->dst safely. Return 'copied' or 'skipped'."""
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        if sha256(dst) == sha256(src):
            return "skipped"

    # Keep both if name collision with different content.
    final = dst
    if final.exists():
        stem, suf, i = final.stem, final.suffix, 1
        while final.exists():
            final = final.with_name(f"{stem}_{i}{suf}")
            i += 1

    tmp = final.with_name(f".{final.name}.part")

    try:
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                chunk = fi.read(CHUNK)
                if not chunk:
                    break
                fo.write(chunk)
            fo.flush()
            os.fsync(fo.fileno())

        if sha256(tmp) != sha256(src):
            raise IOError(f"Checksum mismatch after copy for {src}")

        shutil.copystat(src, tmp)
        os.replace(tmp, final)
        fsync_dir(final.parent)
        return "copied"
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def collect_files(source: Path) -> list[Path]:
    return sorted(
        p for p in source.rglob("*")
        if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith(".")
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Safely import Canon files from SD to HDD by day")
    ap.add_argument("source", type=Path, help="SD card root or DCIM path")
    ap.add_argument("dest", type=Path, help="Destination root on external HDD")
    args = ap.parse_args()

    if not args.source.is_dir():
        print(f"Source not found: {args.source}", file=sys.stderr)
        return 2
    if not args.dest.is_dir():
        print(f"Destination not found (is HDD mounted?): {args.dest}", file=sys.stderr)
        return 2

    # Cleanup stale partials from prior interruption.
    for part in args.dest.rglob(".*.part"):
        part.unlink(missing_ok=True)

    files = collect_files(args.source)
    print(f"Found {len(files)} eligible files")

    copied = skipped = failed = 0
    for i, src in enumerate(files, start=1):
        target_dir = args.dest / day_folder(src)
        target_dir.mkdir(parents=True, exist_ok=True)
        dst = target_dir / src.name
        try:
            result = safe_copy(src, dst)
            if result == "copied":
                copied += 1
            else:
                skipped += 1
            print(f"[{i}/{len(files)}] {result}: {target_dir.name}/{src.name}")
        except KeyboardInterrupt:
            print("\nInterrupted. Safe to rerun.")
            return 130
        except Exception as e:
            failed += 1
            print(f"[{i}/{len(files)}] FAILED {src}: {e}", file=sys.stderr)
            if not args.dest.exists():
                print("Destination disappeared (possibly unplugged). Stopping.", file=sys.stderr)
                break

    print(f"Done. copied={copied} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
