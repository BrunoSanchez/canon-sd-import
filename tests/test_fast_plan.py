import os

import pytest

import canon_import.core as core
from canon_import.cli import import_main
from canon_import.importer import run

quiet = lambda *a, **k: None  # noqa: E731
DAY = "2026-10-27"


def _boom(*a, **k):
    raise AssertionError("sha256_file must not be called")


def _set_mtime(path, delta):
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + delta))


def test_default_plan_and_dry_run_never_hash(dirs, make_file, monkeypatch):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"abc", day=DAY)
    make_file(backup / "2026_10_27" / "IMG_1.CR3", b"abc", day=DAY)
    monkeypatch.setattr(core, "sha256_file", _boom)
    rep = run(sd, backup, dry_run=True, print_fn=quiet, progress=False)
    assert rep.files_skipped == 1 and rep.files_copied == 0
    rep = run(sd, backup, assume_yes=True, print_fn=quiet, progress=False)
    assert rep.files_skipped == 1 and rep.files_copied == 0


def test_dry_run_writes_nothing(dirs, make_file):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"abc", day=DAY)
    run(sd, backup, dry_run=True, print_fn=quiet, progress=False)
    assert list(backup.iterdir()) == []


def test_same_size_different_mtime_is_conflict(dirs, make_file):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"new", day=DAY)
    old = make_file(backup / "2026_10_27" / "IMG_1.CR3", b"old", day=DAY)
    _set_mtime(old, -3600)
    run(sd, backup, assume_yes=True, print_fn=quiet, progress=False)
    assert old.read_bytes() == b"old"
    assert (backup / "2026_10_27" / "IMG_1_1.CR3").read_bytes() == b"new"


def test_different_size_is_conflict(dirs, make_file):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"newer", day=DAY)
    old = make_file(backup / "2026_10_27" / "IMG_1.CR3", b"old", day=DAY)
    run(sd, backup, assume_yes=True, print_fn=quiet, progress=False)
    assert old.read_bytes() == b"old"
    assert (backup / "2026_10_27" / "IMG_1_1.CR3").read_bytes() == b"newer"


@pytest.mark.parametrize("delta,present", [(1.5, True), (2.0, True), (3.0, False)])
def test_mtime_tolerance(dirs, make_file, delta, present):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"abc", day=DAY)
    dst = make_file(backup / "2026_10_27" / "IMG_1.CR3", b"abc", day=DAY)
    _set_mtime(dst, delta)
    rep = run(sd, backup, dry_run=True, print_fn=quiet, progress=False)
    assert (rep.files_skipped == 1) == present


def test_deep_detects_same_size_same_mtime_different_content(dirs, make_file):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"aaa", day=DAY)
    old = make_file(backup / "2026_10_27" / "IMG_1.CR3", b"bbb", day=DAY)
    rep = run(sd, backup, dry_run=True, print_fn=quiet, progress=False)
    assert rep.files_skipped == 1  # fast mode trusts size+mtime
    rep = run(sd, backup, dry_run=True, deep=True, print_fn=quiet, progress=False)
    assert rep.files_skipped == 0
    run(sd, backup, assume_yes=True, deep=True, print_fn=quiet, progress=False)
    assert old.read_bytes() == b"bbb"
    assert (backup / "2026_10_27" / "IMG_1_1.CR3").read_bytes() == b"aaa"


def test_deep_flag_threaded_through_cli(dirs, make_file, monkeypatch):
    sd, backup = dirs
    seen = {}

    def fake_run(*a, **k):
        seen.update(k)
        return run(*a, **{**k, "print_fn": quiet})

    monkeypatch.setattr("canon_import.cli.run", fake_run)
    make_file(sd / "100CANON" / "IMG_1.CR3", b"abc", day=DAY)
    assert import_main([str(sd), str(backup), "--dry-run", "--deep", "--no-progress"]) == 0
    assert seen["deep"] is True and seen["progress"] is False


def test_real_copy_fails_safely_when_replace_raises(dirs, make_file, monkeypatch):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"abc", day=DAY)

    def bad_replace(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(core.os, "replace", bad_replace)
    rep = run(sd, backup, assume_yes=True, print_fn=quiet, progress=False)
    assert rep.failures and rep.files_copied == 0
    day = backup / "2026_10_27"
    assert not (day / "IMG_1.CR3").exists()
    assert list(day.glob(".*.part")) == []
