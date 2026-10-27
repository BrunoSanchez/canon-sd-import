import io

from canon_import.core import copy_verified
from canon_import.importer import run
from canon_import.progress import Progress

quiet = lambda *a, **k: None  # noqa: E731


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


def test_non_tty_output_is_bounded_and_has_percent_and_eta(monkeypatch, capsys):
    bar = Progress("Scanning", total_items=5000, total_bytes=5000 * 1024 * 1024, plain_every=500, plain_interval=1e9)
    for _ in range(5000):
        bar.update(items=1, nbytes=1024 * 1024)
    bar.finish()
    lines = capsys.readouterr().err.strip().splitlines()
    assert 1 < len(lines) <= 15
    assert "%" in lines[0] and "5000/5000" in lines[-1] and "MB/s" in lines[-1]
    assert "ETA" in lines[0]


def test_tty_uses_carriage_return(monkeypatch):
    fake = FakeTTY()
    monkeypatch.setattr("sys.stderr", fake)
    bar = Progress("X", total_items=2)
    bar.update(items=1)
    bar.clear()
    bar.finish()
    out = fake.getvalue()
    assert "\r" in out and out.endswith("\n")


def test_disabled_produces_no_output(dirs, make_file, capsys):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"abc", day="2026-10-27")
    run(sd, backup, assume_yes=True, print_fn=quiet, progress=False)
    assert capsys.readouterr().err == ""


def test_enabled_writes_to_stderr(dirs, make_file, capsys):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"abc", day="2026-10-27")
    run(sd, backup, assume_yes=True, print_fn=quiet)
    err = capsys.readouterr().err
    assert "Scanning" in err and "Copying" in err


def test_copy_callback_totals_file_size(tmp_path):
    src = tmp_path / "a.CR3"
    src.write_bytes(b"x" * 12345)
    got, ver = [], []
    copy_verified(src, tmp_path / "b.CR3", got.append, ver.append)
    assert sum(got) == 12345 and sum(ver) == 12345


def test_prompts_work_with_progress(dirs, make_file, capsys):
    sd, backup = dirs
    make_file(sd / "100CANON" / "IMG_1.CR3", b"abc", day="2026-10-27")
    make_file(sd / "100CANON" / "IMG_2.CR3", b"def", day="2026-10-28")
    answers = iter(["y", "n"])
    prompts = []

    def input_fn(msg):
        prompts.append(msg)
        return next(answers)

    rep = run(sd, backup, input_fn=input_fn, print_fn=quiet)
    assert len(prompts) == 2
    assert rep.files_copied == 1 and rep.declined_days == ["2026_10_28"]
    assert (backup / "2026_10_27" / "IMG_1.CR3").exists()
    assert not (backup / "2026_10_28").exists()
