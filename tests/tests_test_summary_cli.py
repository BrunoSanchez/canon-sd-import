from canon_import.summary import summarize


def test_summary_uses_backup_day_folder(tmp_path, make_file):
    make_file(tmp_path / "2026_10_27" / "a.CR3", b"x" * 100, day="2020-01-01")
    make_file(tmp_path / "2026_10_27" / "b.MP4", b"x" * 50, day="2020-01-01")

    out = summarize(tmp_path)
    assert out == {"2026_10_27": (2, 150)}


def test_summary_uses_mtime_for_sd_style(tmp_path, make_file):
    make_file(tmp_path / "100CANON" / "a.CR3", b"x" * 10, day="2026-03-04")
    out = summarize(tmp_path)
    assert out == {"2026_03_04": (1, 10)}