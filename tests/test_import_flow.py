from canon_import.importer import run


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