"""Group words into short captions and write an ASS subtitle file for libass."""
from __future__ import annotations

import re

import pysubs2

from clipper.transcribe import SENTENCE_END

EDGE_PUNCT = re.compile(r"^[^\w$#@]+|[^\w%]+$")
MAX_GAP = 0.6   # a pause longer than this starts a new caption group
LINGER = 0.3    # keep a group on screen this long after its last word (unless the next starts sooner)
POP = r"\fscx85\fscy85\t(0,80,\fscx100\fscy100)"


def clean(word: str) -> str:
    return EDGE_PUNCT.sub("", word)


def ass_color(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#").upper()
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&"


def _ssa_color(hex_rgb: str, alpha: int = 0) -> pysubs2.Color:
    h = hex_rgb.lstrip("#")
    return pysubs2.Color(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def group_words(words: list[dict], max_words: int = 3, max_chars: int = 15, uppercase: bool = True) -> list[dict]:
    groups: list[list[dict]] = []
    for w in words:
        text = clean(w["w"])
        if not text:
            continue
        item = {"text": text.upper() if uppercase else text, "key": text.lower(), "s": w["s"], "e": w["e"], "raw": w["w"]}
        if groups:
            cur = groups[-1]
            prev = cur[-1]
            joined_len = sum(len(x["text"]) for x in cur) + len(cur) + len(item["text"])
            if (len(cur) < max_words and joined_len <= max_chars
                    and item["s"] - prev["e"] <= MAX_GAP and not SENTENCE_END.search(prev["raw"])):
                cur.append(item)
                continue
        groups.append([item])
    out = []
    for i, g in enumerate(groups):
        end = g[-1]["e"] + LINGER
        if i + 1 < len(groups):
            end = min(end, groups[i + 1][0]["s"])
        end = max(end, g[0]["s"] + 0.05)
        out.append({"start": g[0]["s"], "end": round(end, 3), "words": g})
    return out


def _layout_at(segments: list[dict], t: float) -> str:
    for seg in segments:
        if seg["start"] <= t < seg["end"]:
            return seg["layout"]
    return segments[-1]["layout"] if segments else "fill"


def _ms(t: float) -> int:
    return max(0, int(round(t * 1000)))


def build_ass(groups: list[dict], cfg: dict, segments: list[dict], hook_text: str | None,
              emphasis: set[str]) -> pysubs2.SSAFile:
    c, hk = cfg["captions"], cfg["hook_text"]
    subs = pysubs2.SSAFile()
    subs.info.update({"PlayResX": "1080", "PlayResY": "1920", "WrapStyle": "0", "ScaledBorderAndShadow": "yes"})
    subs.styles["Cap"] = pysubs2.SSAStyle(
        fontname=c["font"], fontsize=c["size"], primarycolor=_ssa_color(c["color"]),
        outlinecolor=_ssa_color("#000000"), backcolor=_ssa_color("#000000", 120),
        bold=False, outline=c["outline"], shadow=c["shadow"],
        alignment=pysubs2.Alignment.MIDDLE_CENTER, marginl=0, marginr=0, marginv=0)
    # BorderStyle 3 = opaque box; libass/VSFilter differ on which colour fills it, so set both to white.
    subs.styles["Hook"] = pysubs2.SSAStyle(
        fontname=c["font"], fontsize=hk["size"], primarycolor=_ssa_color("#000000"),
        outlinecolor=_ssa_color("#FFFFFF"), backcolor=_ssa_color("#FFFFFF"),
        bold=False, borderstyle=3, outline=14, shadow=0,
        alignment=pysubs2.Alignment.TOP_CENTER, marginl=90, marginr=140, marginv=hk["margin_top"])
    if hook_text and hk["enabled"]:
        subs.append(pysubs2.SSAEvent(start=0, end=_ms(hk["duration"]), style="Hook", text=hook_text.upper()))
    hl, base = ass_color(c["highlight_color"]), ass_color(c["color"])
    for g in groups:
        y = c["split_y"] if _layout_at(segments, g["start"]) == "split" else c["y"]
        n = len(g["words"])
        for i, active in enumerate(g["words"]):
            s = g["start"] if i == 0 else active["s"]
            e = g["words"][i + 1]["s"] if i + 1 < n else g["end"]
            if e <= s:
                continue
            parts = [f"{{\\c{hl if (j == i or w['key'] in emphasis) else base}}}{w['text']}"
                     for j, w in enumerate(g["words"])]
            head = f"{{\\an5\\pos({c['x']},{y}){POP if i == 0 else ''}}}"
            subs.append(pysubs2.SSAEvent(start=_ms(s), end=_ms(e), style="Cap", text=head + " ".join(parts)))
    return subs
