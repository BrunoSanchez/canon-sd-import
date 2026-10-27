from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple, Union

EXTS = {
    ".cr2", ".cr3", ".crw", ".jpg", ".jpeg", ".hif", ".heic",
    ".mp4", ".mov", ".mts", ".thm", ".xmp", ".wav",
}
CHUNK = 4 * 1024 * 1024
DAY_FMT = "%Y_%m_%d"
DAY_RE = re.compile(r"^\d{4}_\d{2}_\d{2}$")
PART_GLOB = ".*.part"
MTIME_TOLERANCE = 2.0


class FileInfo(NamedTuple):
    path: Path
    size: int
    mtime: float


class ChecksumError(OSError):
    pass


def human_size(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024 or unit == "TB":
            return f"{int(x)} B" if unit == "B" else f"{x:.2f} {unit}"
        x /= 1024
    return f"{n} B"


def sha256_file(path: Path, progress_cb: Optional[Callable[[int], None]] = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            if progress_cb:
                progress_cb(len(chunk))
    return h.hexdigest()


def day_of(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime(DAY_FMT)


def is_media(path: Path) -> bool:
    return path.is_file() and not path.name.startswith(".") and path.suffix.lower() in EXTS


def _walk(root: Path):
    stack = [str(root)]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    if entry.name.startswith(".") or os.path.splitext(entry.name)[1].lower() not in EXTS:
                        continue
                    if not entry.is_file():
                        continue
                    st = entry.stat()
                except OSError:
                    continue
                yield FileInfo(Path(entry.path), st.st_size, st.st_mtime)


def scan_files(root: Path, progress=None) -> List[FileInfo]:
    """Scan once, collecting (path, size, mtime) so media is never stat'ed again."""
    out: List[FileInfo] = []
    for info in _walk(root):
        out.append(info)
        if progress:
            progress.update(items=1)
    out.sort(key=lambda i: i.path)
    return out


def scan_media(root: Path) -> List[Path]:
    return [i.path for i in scan_files(root)]


def day_from_mtime(mtime: float) -> str:
    return dt.datetime.fromtimestamp(mtime).strftime(DAY_FMT)


def group_by_day(files: List[Union[Path, FileInfo]]) -> Dict[str, List[FileInfo]]:
    groups: Dict[str, List[FileInfo]] = {}
    for f in files:
        if not isinstance(f, FileInfo):
            st = f.stat()
            f = FileInfo(f, st.st_size, st.st_mtime)
        groups.setdefault(day_from_mtime(f.mtime), []).append(f)
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


def copy_verified(src: Path, dst: Path, progress_cb: Optional[Callable[[int], None]] = None,
                  verify_cb: Optional[Callable[[int], None]] = None) -> Path:
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
                if progress_cb:
                    progress_cb(len(chunk))
            fo.flush()
            os.fsync(fo.fileno())
        if tmp.stat().st_size != size or sha256_file(tmp, verify_cb) != h.hexdigest():
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
    failures: List[Tuple[Path, OSError]] = field(default_factory=list)
    sizes: Dict[Path, int] = field(default_factory=dict)

    @property
    def bytes_needed(self) -> int:
        return sum(self.sizes.get(s, 0) for s, _ in self.to_copy)


def _list_dir(day_dir: Path) -> Dict[str, Tuple[int, float]]:
    found: Dict[str, Tuple[int, float]] = {}
    if not day_dir.is_dir():
        return found
    with os.scandir(day_dir) as it:
        for e in it:
            try:
                st = e.stat()
            except OSError:
                continue
            found[e.name] = (st.st_size, st.st_mtime)
    return found


def plan_day(day: str, files: List[Union[Path, FileInfo]], day_dir: Path, deep: bool = False,
             progress=None) -> DayPlan:
    plan = DayPlan(day=day, day_dir=day_dir, exists=day_dir.is_dir())
    reserved = set()
    try:
        existing = _list_dir(day_dir)
    except OSError as e:
        existing = {}
        plan.failures.extend((f.path if isinstance(f, FileInfo) else f, e) for f in files)
        return plan
    hashes: Dict[Path, str] = {}

    def hash_of(path: Path) -> str:
        if path not in hashes:
            hashes[path] = sha256_file(path, (lambda n: progress.update(nbytes=n)) if progress else None)
        return hashes[path]

    def same(info: FileInfo, name: str) -> bool:
        size, mtime = existing[name]
        if size != info.size:
            return False
        if deep:
            return hash_of(day_dir / name) == hash_of(info.path)
        return abs(mtime - info.mtime) <= MTIME_TOLERANCE

    for item in sorted(files, key=lambda f: f.path if isinstance(f, FileInfo) else f):
        src = item.path if isinstance(item, FileInfo) else item
        try:
            if not isinstance(item, FileInfo):
                st = src.stat()
                item = FileInfo(src, st.st_size, st.st_mtime)
            plan.sizes[src] = item.size
            name = src.name
            if name in existing:
                if same(item, name):
                    plan.already_present.append(src)
                    continue
                stem, suffix = Path(name).stem, Path(name).suffix
                collision_re = re.compile(rf"{re.escape(stem)}_\d+{re.escape(suffix)}")
                if any(collision_re.fullmatch(n) and same(item, n) for n in sorted(existing)):
                    plan.already_present.append(src)
                    continue
            taken = lambda n: n in existing or (day_dir / n) in reserved  # noqa: E731
            dst = day_dir / name
            i = 1
            while taken(dst.name):
                dst = day_dir / f"{Path(name).stem}_{i}{Path(name).suffix}"
                i += 1
            reserved.add(dst)
            plan.to_copy.append((src, dst))
        except OSError as e:
            plan.failures.append((src, e))
        finally:
            if progress:
                progress.update(items=1)
    return plan
