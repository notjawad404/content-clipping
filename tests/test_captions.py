from clipper.captions import ass_color, build_ass, clean, group_words
from clipper.config import load_config


def w(text, s, e):
    return {"w": text, "s": s, "e": e}


def seq(*texts, start=0.0, step=0.3):
    return [w(t, start + k * step, start + k * step + 0.25) for k, t in enumerate(texts)]


def texts(groups):
    return [" ".join(x["text"] for x in g["words"]) for g in groups]


def test_clean_strips_edge_punctuation_only():
    assert clean("viral,") == "viral"
    assert clean("don't") == "don't"
    assert clean('"$100!"') == "$100"
    assert clean("50%.") == "50%"


def test_ass_color_is_bgr():
    assert ass_color("#FFE500") == "&H00E5FF&"


def test_group_words_max_three_words():
    groups = group_words(seq("To", "go", "viral,", "you", "have", "to", "do", "something."))
    assert texts(groups) == ["TO GO VIRAL", "YOU HAVE TO", "DO SOMETHING"]


def test_group_words_char_limit_sentence_end_and_gaps():
    words = seq("Extraordinary", "billionaire") + seq("Yes.", "No", start=2.0) + [w("later", 4.0, 4.3)]
    assert texts(group_words(words)) == ["EXTRAORDINARY", "BILLIONAIRE", "YES", "NO", "LATER"]


def test_group_end_lingers_but_never_overlaps_next():
    groups = group_words([w("Hello.", 0.0, 0.5), w("Next", 0.6, 0.9), w("one.", 2.0, 2.3)])
    assert groups[0]["end"] == 0.6
    assert groups[-1]["end"] == 2.6


def test_build_ass_events_positions_and_highlight():
    cfg = load_config()
    groups = group_words(seq("Make", "a", "million", "dollars."))
    segments = [{"start": 0.0, "end": 0.5, "layout": "fill"}, {"start": 0.5, "end": 5.0, "layout": "split"}]
    subs = build_ass(groups, cfg, segments, hook_text="Nobody talks about this", emphasis={"million"})
    hooks = [e for e in subs if e.style == "Hook"]
    caps = [e for e in subs if e.style == "Cap"]
    assert hooks[0].text == "NOBODY TALKS ABOUT THIS" and hooks[0].end == 2500
    assert len(caps) == 4                                         # one event per active word
    assert caps[0].text.startswith("{\\an5\\pos(520,1130)\\fscx85")  # first group, fill layout, pops in
    assert "\\fscx85" not in caps[1].text                           # only the first event of a group pops
    assert "\\pos(520,960)" in caps[3].text                         # second group starts in split layout
    yellow = ass_color("#FFE500")
    assert f"{{\\c{yellow}}}MILLION" in caps[0].text              # emphasis word always highlighted
    assert f"{{\\c{yellow}}}MAKE" in caps[0].text                 # active word highlighted
    assert f"{{\\c{yellow}}}MAKE" not in caps[1].text


def test_build_ass_without_hook():
    cfg = load_config()
    cfg["hook_text"]["enabled"] = False
    subs = build_ass(group_words(seq("Hi.")), cfg, [{"start": 0, "end": 5, "layout": "fill"}], "Hook", set())
    assert [e.style for e in subs] == ["Cap"]


def test_default_caption_and_hook_positions_are_in_safe_zone():
    cfg = load_config()
    c, hk = cfg["captions"], cfg["hook_text"]
    half_width = c["max_chars"] * c["size"] * 0.75 / 2   # ~0.75 em per uppercase Montserrat Black glyph
    assert 65 <= c["x"] - half_width and c["x"] + half_width <= 960
    for y in (c["y"], c["split_y"]):
        assert 270 <= y - c["size"] / 2 and y + c["size"] / 2 <= 1250
    assert hk["margin_top"] >= 270
