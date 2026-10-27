from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from .core import DAY_RE, day_of, human_size, scan_media


def summarize(root: Path) -> Dict[str, Tuple[int, int]]:
    result: Dict[str, Tuple[int, int]] = {}
    for f in scan_media(root):
        try:
            rel = f.relative_to(root)
            day = rel.parts[0] if len(rel.parts) > 1 and DAY_RE.match(rel.parts[0]) else day_of(f)
            size = f.stat().st_size
        except OSError:
            continue
        c, b = result.get(day, (0, 0))
        result[day] = (c + 1, b + size)
    return result


def format_report(root: Path) -> str:
    data = summarize(root)
    lines = [f"=== {root} ==="]
    if not data:
        lines.append("  (no photos or videos)")
        return "\n".join(lines)
    total_c = sum(c for c, _ in data.values())
    total_b = sum(b for _, b in data.values())
    for day in sorted(data):
        c, b = data[day]
        lines.append(f"  {day}  {c:6d} files  {human_size(b):>10}")
    lines.append(f"  TOTAL  {len(data)} days, {total_c} files, {human_size(total_b)}")
    return "\n".join(lines)
