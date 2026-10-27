from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .importer import UserError, run
from .summary import format_report


def import_main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="canon-import")
    ap.add_argument("source", type=Path)
    ap.add_argument("backup", type=Path)
    ap.add_argument("-y", "--yes", action="store_true")
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument("--deep", action="store_true", help="compare same-size files by full SHA-256 instead of size+mtime")
    ap.add_argument("--no-progress", action="store_true", help="disable progress output")
    args = ap.parse_args(argv)
    try:
        report = run(args.source, args.backup, assume_yes=args.yes, dry_run=args.dry_run,
                     deep=args.deep, progress=not args.no_progress)
    except UserError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return report.exit_code


def summary_main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="canon-summary")
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--no-progress", action="store_true", help="disable progress output")
    args = ap.parse_args(argv)
    bad = [p for p in args.paths if not p.is_dir()]
    if bad:
        for p in bad:
            print(f"Not a directory: {p}", file=sys.stderr)
        return 2
    for p in args.paths:
        print(format_report(p, progress=not args.no_progress))
        print()
    return 0
