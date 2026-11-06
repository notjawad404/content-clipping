from collections import namedtuple

from clipper.doctor import Check, check_disk, format_report, listed_names, node_major

Usage = namedtuple("Usage", "total used free")


def test_check_disk_threshold(tmp_path):
    assert check_disk(tmp_path, usage=lambda p: Usage(0, 0, 6 * 1024**3)).ok
    low = check_disk(tmp_path, usage=lambda p: Usage(0, 0, 2 * 1024**3))
    assert not low.ok and "2.0 GB free" in low.detail


def test_listed_names_parses_filters_and_encoders():
    filters = ("Filters:\n  T.. = Timeline support\n"
               " ... ass               V->V       Render ASS subtitles\n"
               " ... subtitles         V->V       Render text subtitles\n")
    encoders = "Encoders:\n V..... = Video\n V....D libx264               libx264 H.264\n"
    assert {"ass", "subtitles"} <= listed_names(filters)
    assert "libx264" in listed_names(encoders)


def test_node_major():
    assert node_major("v22.22.0\n") == 22
    assert node_major("") is None


def test_format_report_shows_fix_for_failures():
    text = format_report([Check("a", True, "fine"), Check("b", False, "missing", "brew install x")])
    assert "OK   a: fine" in text and "FAIL b: missing" in text and "fix: brew install x" in text
    assert text.endswith("Some checks failed; run the fixes above.")
