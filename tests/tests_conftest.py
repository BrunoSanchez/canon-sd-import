import datetime as dt
import os

import pytest


@pytest.fixture
def make_file():
    def _make(path, content=b"data", day="2026-10-27"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        ts = dt.datetime.strptime(day + " 12:00", "%Y-%m-%d %H:%M").timestamp()
        os.utime(path, (ts, ts))
        return path
    return _make


@pytest.fixture
def dirs(tmp_path):
    sd = tmp_path / "sd" / "DCIM" / "100CANON"
    sd.mkdir(parents=True)
    backup = tmp_path / "hdd" / "CanonR50Pictures"
    backup.mkdir(parents=True)
    return sd.parent, backup