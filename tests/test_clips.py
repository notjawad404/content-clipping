import pytest

from clipper.clips import (ClipError, clip_words, compose_post, resolve_all, sentence_end_times,
                           snap_bounds, validate_doc)

CFG = {"length": {"min": 20, "max": 90}, "min_score": 7.0, "max_clips": 8, "max_overlap": 0.5,
       "required_tags": [], "required_text": "", "creator_tag": "", "max_hashtags": 5}


def make_words(n=200):
    # word i spans [i*0.5, i*0.5 + 0.4]; every 10th word ends a sentence
    return [{"i": i, "w": "end." if i % 10 == 9 else "word", "s": i * 0.5, "e": i * 0.5 + 0.4} for i in range(n)]


def make_sentences(words):
    out = []
    for k in range(len(words) // 10):
        a, b = k * 10, k * 10 + 9
        out.append({"id": f"S{k + 1:04d}", "start_word": a, "end_word": b,
                    "start": words[a]["s"], "end": words[b]["e"], "text": "..."})
    return out


def make_clip(cid, first, last, score=8.0):
    return {"id": cid, "start_sentence": first, "end_sentence": last, "hook_text": "BIG HOOK",
            "title": f"title {cid}", "score": score,
            "scores": {"hook": 4, "standalone": 4, "payoff": 4, "emotion": 4, "novelty": 4, "shareability": 4},
            "reason": "because", "emphasis_words": ["million"],
            "post": {"instagram": "Great clip #podcast", "tiktok": "tt", "youtube": "yt", "x": "x post"}}


def doc(*clips):
    return {"video_id": "vid", "clips": list(clips)}


WORDS = make_words()
SENTENCES = make_sentences(WORDS)


def test_snap_bounds_uses_lead_and_tail_limited_by_neighbours():
    assert snap_bounds(WORDS, 10, 49) == (4.92, 25.0)
    assert snap_bounds(WORDS, 0, 9) == (0.0, 5.0)


def test_resolve_accepts_valid_clip():
    result = resolve_all(doc(make_clip("clip_01", "S0002", "S0005")), SENTENCES, WORDS, CFG)
    assert result["rejected"] == []
    c = result["clips"][0]
    assert (c["start"], c["end"], c["duration"]) == (4.92, 25.0, 20.08)
    assert (c["first_word"], c["last_word"]) == (10, 49)
    assert set(c["post"]) == {"instagram", "tiktok", "youtube", "x"}


@pytest.mark.parametrize("clip, reason", [
    (make_clip("clip_01", "S0099", "S0100"), "unknown sentence"),
    (make_clip("clip_01", "S0005", "S0002"), "before start_sentence"),
    (make_clip("clip_01", "S0002", "S0003"), "outside 20-90s"),
    (make_clip("clip_01", "S0002", "S0005", score=6.5), "below min_score"),
])
def test_resolve_rejects_with_reason(clip, reason):
    result = resolve_all(doc(clip), SENTENCES, WORDS, CFG)
    assert result["clips"] == []
    assert reason in result["rejected"][0]["reason"]


def test_resolve_drops_overlap_and_respects_max_clips():
    a = make_clip("clip_01", "S0002", "S0006", score=9.0)
    b = make_clip("clip_02", "S0003", "S0007", score=8.0)  # mostly inside a
    c = make_clip("clip_03", "S0010", "S0014", score=7.5)
    result = resolve_all(doc(a, b, c), SENTENCES, WORDS, {**CFG, "max_clips": 1})
    assert [x["id"] for x in result["clips"]] == ["clip_01"]
    reasons = {r["id"]: r["reason"] for r in result["rejected"]}
    assert "overlaps clip_01" in reasons["clip_02"]
    assert "max_clips" in reasons["clip_03"]


def test_schema_violation_raises():
    bad = make_clip("clip_01", "S0002", "S0005")
    del bad["post"]["x"]
    with pytest.raises(ClipError, match="post"):
        validate_doc(doc(bad))


def test_duplicate_ids_raise():
    with pytest.raises(ClipError, match="duplicate"):
        validate_doc(doc(make_clip("clip_01", "S0002", "S0005"), make_clip("clip_01", "S0010", "S0014")))


def test_compose_post_injects_required_text_once_and_caps_hashtags():
    cfg = {**CFG, "required_text": "Clip from @pod", "creator_tag": "@pod",
           "required_tags": ["#podclips"], "max_hashtags": 3}
    out = compose_post("So true #a #b #c #d", cfg, "instagram")
    assert out == "So true\nClip from @pod\n#podclips #a #b"


def test_compose_post_truncates_x_to_280():
    out = compose_post("word " * 100, {**CFG, "required_text": "Clip from @pod"}, "x")
    assert len(out) <= 280
    assert out.endswith("…\nClip from @pod")


def test_clip_words_are_relative_to_clip_start():
    cw = clip_words(WORDS, {"start": 4.92, "first_word": 10, "last_word": 12})
    assert [x["i"] for x in cw] == [10, 11, 12]
    assert cw[0]["s"] == pytest.approx(0.08)


def test_sentence_end_times():
    cw = [{"w": "Hi", "s": 0.0, "e": 0.2}, {"w": "there.", "s": 0.3, "e": 0.6}, {"w": "Ok", "s": 1.0, "e": 1.2}]
    assert sentence_end_times(cw) == [0.6]


def test_snap_bounds_never_cuts_into_own_words_when_neighbours_overlap():
    words = [{"w": "a", "s": 0.0, "e": 1.05}, {"w": "b", "s": 1.0, "e": 1.5},
             {"w": "c", "s": 2.0, "e": 2.6}, {"w": "d", "s": 2.5, "e": 3.0}]
    start, end = snap_bounds(words, 1, 2)
    assert start <= 1.0 and end >= 2.6
    clip = {"start": start, "first_word": 1, "last_word": 2}
    assert clip_words(words, clip)[0]["s"] >= 0.0


def test_compose_post_keeps_numbers_and_mid_sentence_hashtags():
    out = compose_post("The #1 mistake founders make. Why #AI changes everything", CFG, "instagram")
    assert out == "The #1 mistake founders make. Why #AI changes everything"


def test_compose_post_midsentence_tags_count_toward_cap_and_are_not_duplicated():
    cfg = {**CFG, "required_tags": ["#req"], "max_hashtags": 3}
    out = compose_post("Why #AI wins #a #b #c", cfg, "instagram")
    assert out == "Why #AI wins\n#req #a"


def test_compose_post_trailing_tags_on_own_line_are_relocated():
    out = compose_post("Big idea\n#x #X #y", CFG, "tiktok")
    assert out == "Big idea\n#x #y"
