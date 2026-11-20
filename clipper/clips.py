"""Validate Claude's clips.json, turn sentence IDs into exact times, apply campaign post rules."""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

from clipper.jobs import Job
from clipper.transcribe import SENTENCE_END

SCHEMA_PATH = Path(__file__).parent / "schemas" / "clips.schema.json"
LEAD = 0.08       # seconds of air before the first word
MAX_TAIL = 0.4    # seconds of air after the last word (never into the next word)
PLATFORMS = ("instagram", "tiktok", "youtube", "x")
X_LIMIT = 280
HASHTAG = re.compile(r"(?<!\w)#[A-Za-z]\w*")  # "#1" is a number, not a tag
TRAILING_TAG = re.compile(r"\s*(?<!\w)(#[A-Za-z]\w*)\s*$")


class ClipError(Exception):
    pass


def validate_doc(doc: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        where = "/".join(str(p) for p in exc.absolute_path)
        raise ClipError(f"clips.json invalid at '{where}': {exc.message}") from exc
    ids = [c["id"] for c in doc["clips"]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ClipError(f"clips.json has duplicate clip ids: {', '.join(dupes)}")


def snap_bounds(words: list[dict], first_i: int, last_i: int) -> tuple[float, float]:
    start = max(0.0, words[first_i]["s"] - LEAD)
    if first_i > 0:
        start = max(start, words[first_i - 1]["e"])
    end = words[last_i]["e"] + MAX_TAIL
    if last_i + 1 < len(words):
        end = min(end, words[last_i + 1]["s"])
    # Overlapping ASR word times must never pull the cut into the clip's own first/last word.
    start = min(start, words[first_i]["s"])
    end = max(end, words[last_i]["e"])
    return round(start, 3), round(end, 3)


def overlap_ratio(a: dict, b: dict) -> float:
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    shorter = min(a["end"] - a["start"], b["end"] - b["start"])
    return inter / shorter if shorter > 0 else 0.0


def compose_post(text: str, cfg: dict, platform: str) -> str:
    # Only a trailing run of hashtags is relocated to the tag line; tags used mid-sentence stay in the body.
    found: list[str] = []
    body = text.rstrip()
    while (m := TRAILING_TAG.search(body)):
        found.insert(0, m.group(1))
        body = body[: m.start()]
    body = "\n".join(re.sub(r"[ \t]{2,}", " ", line).strip() for line in body.splitlines()).strip()
    inline = {t.lower() for t in HASHTAG.findall(body)}
    required = [t if t.startswith("#") else f"#{t}" for t in cfg.get("required_tags", [])]
    tags: list[str] = []
    for tag in required + found:
        if tag.lower() not in {t.lower() for t in tags} | inline:
            tags.append(tag)
    kept_required = sum(1 for t in tags if t in required)
    tags = tags[: max(cfg.get("max_hashtags", 5) - len(inline), kept_required)]
    tail_lines: list[str] = []
    seen = body.lower()
    for extra in (cfg.get("required_text", ""), cfg.get("creator_tag", "")):
        if extra and extra.lower() not in seen:
            tail_lines.append(extra)
            seen += "\n" + extra.lower()
    if tags:
        tail_lines.append(" ".join(tags))
    tail = "\n".join(tail_lines)
    if platform == "x" and len(body) + len(tail) + 1 > X_LIMIT:
        room = X_LIMIT - len(tail) - 1
        if room < 2:
            raise ClipError(f"required text and tags alone exceed X's {X_LIMIT} characters")
        body = body[: room - 1].rstrip() + "…"
    return "\n".join(part for part in (body, tail) if part)


def resolve_all(doc: dict, sentences: list[dict], words: list[dict], cfg: dict) -> dict:
    validate_doc(doc)
    by_id = {s["id"]: s for s in sentences}
    length = cfg["length"]
    max_overlap = cfg.get("max_overlap", 0.5)
    accepted: list[dict] = []
    rejected: list[dict] = []
    for clip in sorted(doc["clips"], key=lambda c: c["score"], reverse=True):
        try:
            first, last = by_id.get(clip["start_sentence"]), by_id.get(clip["end_sentence"])
            if first is None or last is None:
                raise ClipError("unknown sentence id")
            if first["start_word"] > last["end_word"]:
                raise ClipError("end_sentence comes before start_sentence")
            if clip["score"] < cfg["min_score"]:
                raise ClipError(f"score {clip['score']} below min_score {cfg['min_score']}")
            start, end = snap_bounds(words, first["start_word"], last["end_word"])
            duration = round(end - start, 3)
            if not length["min"] <= duration <= length["max"]:
                raise ClipError(f"duration {duration:.1f}s outside {length['min']}-{length['max']}s")
            resolved = {**clip, "start": start, "end": end, "duration": duration,
                        "first_word": first["start_word"], "last_word": last["end_word"],
                        "post": {p: compose_post(clip["post"][p], cfg, p) for p in PLATFORMS}}
            for other in accepted:
                if overlap_ratio(resolved, other) > max_overlap:
                    raise ClipError(f"overlaps {other['id']} by more than {max_overlap:.0%}")
            if len(accepted) >= cfg["max_clips"]:
                raise ClipError(f"beyond max_clips ({cfg['max_clips']})")
            accepted.append(resolved)
        except ClipError as exc:
            rejected.append({"id": clip["id"], "title": clip["title"], "reason": str(exc)})
    return {"video_id": doc["video_id"], "clips": accepted, "rejected": rejected}


def clip_words(words: list[dict], clip: dict) -> list[dict]:
    off = clip["start"]
    return [{**w, "s": round(w["s"] - off, 3), "e": round(w["e"] - off, 3)}
            for w in words[clip["first_word"] : clip["last_word"] + 1]]


def sentence_end_times(cwords: list[dict]) -> list[float]:
    return [w["e"] for w in cwords if SENTENCE_END.search(w["w"])]


def run(job: Job, cfg: dict) -> dict:
    result = resolve_all(job.read_json(job.clips), job.read_json(job.sentences_json), job.read_json(job.words), cfg)
    job.write_json(job.clips_resolved, result)
    return result
