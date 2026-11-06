import os

from clipper.jobs import is_fresh, job_for, timed


def make_job(tmp_path):
    job = job_for("abc123", jobs_dir=tmp_path / "jobs", output_dir=tmp_path / "out")
    job.ensure_dirs()
    return job


def test_job_paths(tmp_path):
    job = make_job(tmp_path)
    assert job.words == tmp_path / "jobs" / "abc123" / "words.json"
    assert job.out == tmp_path / "out" / "abc123"
    assert job.src_dir.is_dir() and job.render_dir.is_dir() and job.out.is_dir()


def test_audio_glob(tmp_path):
    job = make_job(tmp_path)
    assert job.audio() is None
    (job.root / "audio.webm").write_bytes(b"x")
    assert job.audio().name == "audio.webm"


def test_json_roundtrip(tmp_path):
    job = make_job(tmp_path)
    job.write_json(job.meta, {"title": "Ünïcode"})
    assert job.read_json(job.meta) == {"title": "Ünïcode"}


def test_is_fresh(tmp_path):
    inp, out = tmp_path / "in.txt", tmp_path / "out.txt"
    assert not is_fresh(out, [inp])
    inp.write_text("a")
    out.write_text("b")
    os.utime(inp, (100, 100))
    os.utime(out, (200, 200))
    assert is_fresh(out, [inp])
    assert is_fresh(out, [inp, tmp_path / "missing.yaml"])  # missing inputs are ignored
    os.utime(inp, (300, 300))
    assert not is_fresh(out, [inp])


def test_timed_records_stage(tmp_path):
    job = make_job(tmp_path)
    with timed(job, "transcribe"):
        pass
    assert "transcribe" in job.read_json(job.timings)
