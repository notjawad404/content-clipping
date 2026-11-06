from clipper.transcribe import build_sentences, format_timestamp, sentences_txt, tokens_to_words


def w(i, text, s, e):
    return {"i": i, "w": text, "s": s, "e": e}


def test_tokens_to_words_joins_subwords():
    tokens = [(" Hel", 0.0, 0.2), ("lo", 0.2, 0.4), (" world", 0.5, 0.9), (".", 0.9, 0.95)]
    assert tokens_to_words(tokens) == [
        {"i": 0, "w": "Hello", "s": 0.0, "e": 0.4},
        {"i": 1, "w": "world.", "s": 0.5, "e": 0.95},
    ]


def test_first_token_without_space_starts_a_word():
    assert tokens_to_words([("Hi", 0.0, 0.3)]) == [{"i": 0, "w": "Hi", "s": 0.0, "e": 0.3}]


def test_blank_tokens_are_skipped():
    assert tokens_to_words([(" ", 0.0, 0.1), (" ok", 0.1, 0.3)])[0]["w"] == "ok"


def test_build_sentences_splits_on_punctuation_and_gaps():
    words = [w(0, "Hello", 0.0, 0.3), w(1, "there.", 0.3, 0.6),
             w(2, "So", 0.7, 0.8), w(3, "anyway", 0.8, 1.2),
             w(4, "next", 3.0, 3.3), w(5, "thing?", 3.3, 3.6)]
    s = build_sentences(words)
    assert [x["text"] for x in s] == ["Hello there.", "So anyway", "next thing?"]
    assert s[1] == {"id": "S0002", "start_word": 2, "end_word": 3, "start": 0.7, "end": 1.2, "text": "So anyway"}
    assert (s[2]["start"], s[2]["end"]) == (3.0, 3.6)


def test_build_sentences_forces_break_on_max_words():
    words = [w(i, "word", i * 0.3, i * 0.3 + 0.2) for i in range(7)]
    assert [x["end_word"] for x in build_sentences(words, max_words=3)] == [2, 5, 6]


def test_format_timestamp_and_txt():
    assert format_timestamp(5025.7) == "1:23:45"
    assert sentences_txt([{"id": "S0001", "start": 12.0, "text": "Hi."}]) == "S0001 [0:00:12] Hi.\n"
