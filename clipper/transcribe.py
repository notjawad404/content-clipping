"""Word-level transcription with parakeet-mlx, plus sentence building for Claude."""
from __future__ import annotations

import re
from pathlib import Path

from clipper.jobs import Job

DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v2"
SENTENCE_END = re.compile(r"[.?!][\"'”’)]*$")


def tokens_to_words(tokens: list[tuple[str, float, float]]) -> list[dict]:
    """Join sub-word tokens into words. A token that starts with whitespace starts a new word."""
    words: list[dict] = []
    for text, start, end in tokens:
        piece = text.strip()
        if not piece:
            continue
        if text[0].isspace() or not words:
            words.append({"i": len(words), "w": piece, "s": round(start, 3), "e": round(end, 3)})
        else:
            words[-1]["w"] += piece
            words[-1]["e"] = round(end, 3)
    return words


def build_sentences(words: list[dict], max_gap: float = 1.2, max_words: int = 50) -> list[dict]:
    sentences: list[dict] = []
    start_i = 0
    for i, word in enumerate(words):
        is_last = i == len(words) - 1
        ends = bool(SENTENCE_END.search(word["w"]))
        long_gap = not is_last and words[i + 1]["s"] - word["e"] > max_gap
        too_long = i - start_i + 1 >= max_words
        if is_last or ends or long_gap or too_long:
            chunk = words[start_i : i + 1]
            sentences.append({
                "id": f"S{len(sentences) + 1:04d}",
                "start_word": start_i,
                "end_word": i,
                "start": chunk[0]["s"],
                "end": chunk[-1]["e"],
                "text": " ".join(x["w"] for x in chunk),
            })
            start_i = i + 1
    return sentences


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def sentences_txt(sentences: list[dict]) -> str:
    return "".join(f"{s['id']} [{format_timestamp(s['start'])}] {s['text']}\n" for s in sentences)


def transcribe_audio(audio_path: Path, model_id: str = DEFAULT_MODEL) -> list[dict]:
    from parakeet_mlx import from_pretrained  # heavy import: keep it lazy

    model = from_pretrained(model_id)
    result = model.transcribe(str(audio_path), chunk_duration=120.0, overlap_duration=15.0)
    tokens: list[tuple[str, float, float]] = []
    for sentence in result.sentences:
        for j, tok in enumerate(sentence.tokens):
            text = tok.text if j else " " + tok.text.lstrip()  # each parakeet sentence starts a new word
            tokens.append((text, tok.start, tok.end))
    return tokens_to_words(tokens)


def run(job: Job, model_id: str = DEFAULT_MODEL) -> list[dict]:
    audio = job.audio()
    if audio is None:
        raise FileNotFoundError(f"No audio file in {job.root}; run `clipper prepare` first")
    words = transcribe_audio(audio, model_id)
    sentences = build_sentences(words)
    job.write_json(job.words, words)
    job.write_json(job.sentences_json, sentences)
    job.sentences_txt.write_text(sentences_txt(sentences))
    return sentences
