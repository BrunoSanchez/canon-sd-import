from canon_import.importer import run


def test_planning_failure_does_not_stop_other_files(dirs, make_file, monkeypatch):
    sd, backup = dirs
    failing = make_file(sd / "100CANON" / "IMG_0001.CR3", b"conflict", day="2026-10-27")
    make_file(sd / "100CANON" / "IMG_0002.CR3", b"copy me", day="2026-10-27")
    make_file(backup / "2026_10_27" / "IMG_0001.CR3", b"not same", day="2026-10-27")

    import canon_import.core

    original_sha256_file = canon_import.core.sha256_file

    def fail_for_one_file(path):
        if path == failing:
            raise PermissionError("unreadable source")
        return original_sha256_file(path)

    monkeypatch.setattr(canon_import.core, "sha256_file", fail_for_one_file)

    rep = run(sd, backup, assume_yes=True, print_fn=lambda *a, **k: None)

    assert rep.files_copied == 1
    assert (backup / "2026_10_27" / "IMG_0002.CR3").read_bytes() == b"copy me"
    assert rep.failures == ["2026_10_27/IMG_0001.CR3: unreadable source"]


def test_import_creates_day_folder_and_copies_file(dirs, make_file):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_0001.CR3", b"abc", day="2026-10-27")

    rep = run(sd, backup, assume_yes=True, print_fn=lambda *a, **k: None)

    assert rep.files_copied == 1
    assert (backup / "2026_10_27" / "IMG_0001.CR3").read_bytes() == b"abc"


def test_second_run_is_idempotent(dirs, make_file):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_0001.CR3", b"abc", day="2026-10-27")

    run(sd, backup, assume_yes=True, print_fn=lambda *a, **k: None)
    rep2 = run(sd, backup, assume_yes=True, print_fn=lambda *a, **k: None)

    assert rep2.files_copied == 0
    assert rep2.files_skipped >= 1


def test_never_overwrites_conflicting_name(dirs, make_file):
    sd, backup = dirs
    make_file(backup / "2026_10_27" / "IMG_0001.CR3", b"old", day="2026-10-27")
    make_file(sd / "100CANON" / "IMG_0001.CR3", b"new", day="2026-10-27")

    rep = run(sd, backup, assume_yes=True, print_fn=lambda *a, **k: None)
    rep2 = run(sd, backup, assume_yes=True, print_fn=lambda *a, **k: None)

    assert rep.files_copied == 1
    assert (backup / "2026_10_27" / "IMG_0001.CR3").read_bytes() == b"old"
    assert (backup / "2026_10_27" / "IMG_0001_1.CR3").read_bytes() == b"new"
    assert rep2.files_copied == 0
    assert rep2.files_skipped == 1
    assert not (backup / "2026_10_27" / "IMG_0001_2.CR3").exists()