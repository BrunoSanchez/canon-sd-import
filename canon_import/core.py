from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

EXTS = {
    ".cr2", ".cr3", ".crw", ".jpg", ".jpeg", ".hif", ".heic",
    ".mp4", ".mov", ".mts", ".thm", ".xmp", ".wav",
}
CHUNK = 4 * 1024 * 1024
DAY_FMT = "%Y_%m_%d"
DAY_RE = re.compile(r"^\d{4}_\d{2}_\d{2}$")
PART_GLOB = ".*.part"


class ChecksumError(OSError):
    pass


def human_size(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024 or unit == "TB":
            return f"{int(x)} B" if unit == "B" else f"{x:.2f} {unit}"
        x /= 1024
    return f"{n} B"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def day_of(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime(DAY_FMT)


def is_media(path: Path) -> bool:
    return path.is_file() and not path.name.startswith(".") and path.suffix.lower() in EXTS


def scan_media(root: Path) -> List[Path]:
    return sorted(p for p in root.rglob("*") if is_media(p))


def group_by_day(files: List[Path]) -> Dict[str, List[Path]]:
    groups: Dict[str, List[Path]] = {}
    for f in files:
        groups.setdefault(day_of(f), []).append(f)
    return groups


def fsync_dir(d: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def unique_name(target: Path) -> Path:
    if not target.exists():
        return target
    i = 1
    while True:
        cand = target.with_name(f"{target.stem}_{i}{target.suffix}")
        if not cand.exists():
            return cand
        i += 1


def copy_verified(src: Path, dst: Path) -> Path:
    if dst.exists():
        raise FileExistsError(str(dst))
    tmp = dst.with_name(f".{dst.name}.part")
    try:
        h = hashlib.sha256()
        size = 0
        with open(src, "rb") as fi, open(tmp, "wb") as fo:
            while True:
                chunk = fi.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                size += len(chunk)
                fo.write(chunk)
            fo.flush()
            os.fsync(fo.fileno())
        if tmp.stat().st_size != size or sha256_file(tmp) != h.hexdigest():
            raise ChecksumError(f"Verification failed for {src.name}")
        shutil.copystat(src, tmp)
        os.replace(tmp, dst)
        fsync_dir(dst.parent)
        return dst
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def cleanup_partials(root: Path) -> int:
    n = 0
    for part in root.rglob(PART_GLOB):
        if part.is_file():
            try:
                part.unlink()
                n += 1
            except OSError:
                pass
    return n


@dataclass
class DayPlan:
    day: str
    day_dir: Path
    exists: bool
    to_copy: List[tuple] = field(default_factory=list)
    already_present: List[Path] = field(default_factory=list)

    @property
    def bytes_needed(self) -> int:
        return sum(s.stat().st_size for s, _ in self.to_copy)


def plan_day(day: str, files: List[Path], day_dir: Path) -> DayPlan:
    plan = DayPlan(day=day, day_dir=day_dir, exists=day_dir.is_dir())
    reserved = set()
    for src in sorted(files):
        dst = day_dir / src.name
        if dst.exists():
            if dst.stat().st_size == src.stat().st_size and sha256_file(dst) == sha256_file(src):
                plan.already_present.append(src)
                continue
            dst = unique_name(dst)
        while dst in reserved:
            dst = dst.with_name(f"{dst.stem}_x{dst.suffix}")
        reserved.add(dst)
        plan.to_copy.append((src, dst))
    return plan
