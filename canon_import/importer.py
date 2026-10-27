from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List

from .core import cleanup_partials, copy_verified, group_by_day, human_size, plan_day, scan_files
from .progress import Progress
from .summary import format_report


class UserError(Exception):
    pass


@dataclass
class Report:
    created_days: List[str] = field(default_factory=list)
    updated_days: List[str] = field(default_factory=list)
    up_to_date_days: List[str] = field(default_factory=list)
    declined_days: List[str] = field(default_factory=list)
    files_copied: int = 0
    bytes_copied: int = 0
    files_skipped: int = 0
    failures: List[str] = field(default_factory=list)
    aborted: bool = False

    @property
    def exit_code(self) -> int:
        return 1 if (self.failures or self.aborted) else 0


def _inside(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or b in a.parents


def print_changes(r: Report, print_fn: Callable[..., None] = print) -> None:
    print_fn("\n=== Summary of changes ===")
    print_fn(f"  New day folders created : {len(r.created_days)} {r.created_days}")
    print_fn(f"  Existing folders updated: {len(r.updated_days)} {r.updated_days}")
    print_fn(f"  Already up to date      : {len(r.up_to_date_days)}")
    print_fn(f"  Declined by you         : {len(r.declined_days)} {r.declined_days}")
    print_fn(f"  Files copied            : {r.files_copied} ({human_size(r.bytes_copied)})")
    print_fn(f"  Files already present   : {r.files_skipped}")
    print_fn(f"  Failures                : {len(r.failures)}")
    for f in r.failures:
        print_fn(f"    - {f}")
    if r.aborted:
        print_fn("  RUN WAS INTERRUPTED - re-run to resume safely.")


LARGE_FILE = 64 * 1024 * 1024


def run(source: Path, backup: Path, assume_yes=False, dry_run=False, input_fn=input, print_fn=print,
        deep=False, progress=True) -> Report:
    source, backup = Path(source), Path(backup)
    if not source.is_dir():
        raise UserError(f"SD card folder not found: {source}")
    if not backup.is_dir():
        raise UserError(f"Backup folder not found: {backup}\nIs the HDD mounted?")
    if _inside(source, backup) or _inside(backup, source):
        raise UserError("Source and backup folders must not contain each other.")

    report = Report()
    if not dry_run:
        cleanup_partials(backup)

    scan_bar = Progress("Scanning", enabled=progress)
    files = scan_files(source, scan_bar)
    scan_bar.finish()
    groups = group_by_day(files)
    plans = []
    plan_bar = Progress("Planning (deep)" if deep else "Planning", total_items=len(files),
                        enabled=progress)
    for d in sorted(groups):
        day_dir = backup / d
        legacy_dir = backup / d.replace("_", "-")
        if not day_dir.exists() and legacy_dir.is_dir():
            day_dir = legacy_dir
        plan = plan_day(d, groups[d], day_dir, deep=deep, progress=plan_bar)
        plans.append(plan)
        report.failures.extend(f"{d}/{src.name}: {error}" for src, error in plan.failures)
    plan_bar.finish()
    print_fn(f"Found {len(files)} photo/video files on the SD card across {len(plans)} day(s).\n")

    for p in plans:
        report.files_skipped += len(p.already_present)
        if not p.to_copy:
            report.up_to_date_days.append(p.day)

    pending = [p for p in plans if p.to_copy]
    for p in plans:
        if not p.to_copy:
            status = "already backed up"
        elif p.exists:
            status = f"EXISTING folder, {len(p.to_copy)} missing file(s), {human_size(p.bytes_needed)}"
        else:
            status = f"NEW folder, {len(p.to_copy)} file(s), {human_size(p.bytes_needed)}"
        print_fn(f"  {p.day}: {status}")
    print_fn("")

    if dry_run:
        print_fn("Dry run: nothing was copied.")
        return report

    bar = Progress("Copying", enabled=progress)
    if assume_yes:
        bar.add_total(sum(len(p.to_copy) for p in pending), sum(p.bytes_needed for p in pending))

    accept_all = assume_yes
    for idx, p in enumerate(pending):
        if not accept_all:
            kind = f"Add {len(p.to_copy)} missing file(s) to existing folder" if p.exists else f"Create new folder and copy {len(p.to_copy)} file(s) into"
            bar.clear()
            ans = input_fn(f"{kind} {p.day_dir.name} ({human_size(p.bytes_needed)})? [y]es / [n]o / [a]ll / [q]uit: ").strip().lower()
            if ans in ("q", "quit"):
                report.aborted = True
                break
            if ans in ("a", "all"):
                accept_all = True
                rest = pending[idx:]
            elif ans in ("y", "yes"):
                rest = [p]
            else:
                report.declined_days.append(p.day)
                continue
            bar.add_total(sum(len(q.to_copy) for q in rest), sum(q.bytes_needed for q in rest))

        try:
            free = shutil.disk_usage(backup).free
            if p.bytes_needed > free:
                report.failures.append(f"{p.day}: not enough free space")
                continue
            p.day_dir.mkdir(exist_ok=True)
        except OSError as e:
            report.failures.append(f"{p.day}: {e}")
            if not backup.is_dir():
                report.aborted = True
                break
            continue
        copied_here = 0
        for src, dst in p.to_copy:
            size = p.sizes.get(src, 0)
            state = {"done": 0, "ver": 0}

            def on_copy(n, name=src.name, size=size, state=state):
                state["done"] += n
                note = name
                if size >= LARGE_FILE:
                    note += f" {state['done'] * 100 // max(size, 1)}%"
                bar.update(nbytes=n, note=note)

            def on_verify(n, name=src.name, size=size, state=state):
                state["ver"] += n
                bar.set_note(f"verifying {name} {state['ver'] * 100 // max(size, 1)}%")

            try:
                copy_verified(src, dst, on_copy, on_verify)
                copied_here += 1
                report.files_copied += 1
                report.bytes_copied += size
                bar.update(items=1)
            except Exception as e:
                report.failures.append(f"{p.day}/{src.name}: {e}")
                bar.update(items=1)
                if not backup.is_dir():
                    report.aborted = True
                    break
        if copied_here:
            (report.updated_days if p.exists else report.created_days).append(p.day)
        if report.aborted:
            break

    bar.finish()
    print_changes(report, print_fn)
    if backup.is_dir():
        print_fn("\nFinal backup contents:")
        print_fn(format_report(backup, progress=progress))
    return report
