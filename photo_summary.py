#!/usr/bin/env python3
"""Summarize photo/video storage by day for one or more roots.

This tool is read-only and safe: it never writes, renames, or deletes files.
It groups eligible files by YYYY-MM-DD (from mtime) and prints counts + size.
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict
from pathlib import Path

EXTS = {".cr2", ".cr3", ".crw", ".jpg", ".jpeg", ".mp4", ".mov", ".thm", ".xmp", ".heic", ".hif"}


def fmt_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return f"{x:.2f} {u}"
        x /= 1024
    return f"{n} B"


def day_of(p: Path) -> str:
    return dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")


def scan(root: Path):
    by_day = defaultdict(lambda: {"count": 0, "bytes": 0})
    total_count = 0
    total_bytes = 0

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() not in EXTS:
            continue
        try:
            sz = p.stat().st_size
            d = day_of(p)
        except OSError:
            continue
        by_day[d]["count"] += 1
        by_day[d]["bytes"] += sz
        total_count += 1
        total_bytes += sz

    return by_day, total_count, total_bytes


def print_report(root: Path) -> None:
    by_day, total_count, total_bytes = scan(root)
    print(f"\n=== {root} ===")
    if not by_day:
        print("No eligible files found.")
        return

    print(f"Total files: {total_count}")
    print(f"Total size : {fmt_bytes(total_bytes)}")
    print("\nBy day:")
    for d in sorted(by_day.keys()):
        c = by_day[d]["count"]
        b = by_day[d]["bytes"]
        print(f"  {d}  files={c:6d}  size={fmt_bytes(b)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize photos/videos by day and size")
    ap.add_argument("paths", nargs="+", type=Path, help="One or more roots (e.g., SD and HDD)")
    args = ap.parse_args()

    bad = [p for p in args.paths if not p.is_dir()]
    if bad:
        for p in bad:
            print(f"Not a directory: {p}")
        return 2

    for p in args.paths:
        print_report(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
