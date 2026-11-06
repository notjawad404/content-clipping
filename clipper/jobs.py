"""Per-video working folders, freshness checks and stage timings."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from clipper.env import JOBS_DIR, OUTPUT_DIR


@dataclass(frozen=True)
class Job:
    video_id: str
    root: Path
    out: Path

    @property
    def job_file(self) -> Path:
        return self.root / "job.json"

    @property
    def meta(self) -> Path:
        return self.root / "meta.json"

    @property
    def words(self) -> Path:
        return self.root / "words.json"

    @property
    def sentences_json(self) -> Path:
        return self.root / "sentences.json"

    @property
    def sentences_txt(self) -> Path:
        return self.root / "sentences.txt"

    @property
    def clips(self) -> Path:
        return self.root / "clips.json"

    @property
    def clips_resolved(self) -> Path:
        return self.root / "clips.resolved.json"

    @property
    def overrides(self) -> Path:
        return self.root / "overrides.yaml"

    @property
    def results(self) -> Path:
        return self.root / "results.json"

    @property
    def timings(self) -> Path:
        return self.root / "timings.json"

    @property
    def src_dir(self) -> Path:
        return self.root / "src"

    @property
    def crops_dir(self) -> Path:
        return self.root / "crops"

    @property
    def render_dir(self) -> Path:
        return self.root / "render"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def frames_dir(self) -> Path:
        return self.root / "frames"

    def audio(self) -> Path | None:
        matches = sorted(self.root.glob("audio.*"))
        return matches[0] if matches else None

    def ensure_dirs(self) -> None:
        for d in (self.root, self.out, self.src_dir, self.crops_dir, self.render_dir, self.logs_dir, self.frames_dir):
            d.mkdir(parents=True, exist_ok=True)

    def read_json(self, path: Path) -> Any:
        return json.loads(path.read_text())

    def write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def job_for(video_id: str, jobs_dir: Path = JOBS_DIR, output_dir: Path = OUTPUT_DIR) -> Job:
    return Job(video_id=video_id, root=jobs_dir / video_id, out=output_dir / video_id)


def is_fresh(output: Path, inputs: list[Path]) -> bool:
    """True when `output` exists and is at least as new as every input that exists."""
    if not output.exists():
        return False
    out_mtime = output.stat().st_mtime
    return all(out_mtime >= p.stat().st_mtime for p in inputs if p.exists())


@contextmanager
def timed(job: Job, stage: str) -> Iterator[None]:
    start = time.monotonic()
    try:
        yield
    finally:
        data = job.read_json(job.timings) if job.timings.exists() else {}
        data[stage] = round(time.monotonic() - start, 1)
        job.write_json(job.timings, data)
