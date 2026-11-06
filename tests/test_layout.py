from clipper.layout import (Face, assign_tracks, fill_box, merge_short_shots, plan_clip, plan_shot,
                            split_box, zoom_box)

SRC_W, SRC_H = 1920, 1080
LEFT = (400.0, 300.0, 200.0, 200.0)
RIGHT = (1300.0, 300.0, 200.0, 200.0)


def mar(talking: bool, k: int) -> float:
    return 0.4 if talking and k % 2 else 0.1


def two_person(duration, a_talks, b_talks, fps=5.0):
    out = []
    for k in range(int(duration * fps)):
        t = k / fps
        out.append([Face(t, LEFT, mar(a_talks(t), k)), Face(t, RIGHT, mar(b_talks(t), k))])
    return out


def test_fill_box_is_9_16_even_and_clamped():
    assert fill_box(500.0, SRC_W, SRC_H) == [196, 2, 606, 1076]
    x, y, w, h = fill_box(1900.0, SRC_W, SRC_H)
    assert x + w <= SRC_W and x % 2 == 0 and w % 2 == 0 and h % 2 == 0


def test_fill_box_on_vertical_source_uses_whole_frame():
    assert fill_box(540.0, 1080, 1920) == [0, 0, 1080, 1920]


def test_split_box_is_9_8_inside_frame():
    x, y, w, h = split_box(LEFT, SRC_W, SRC_H)
    assert abs(w / h - 9 / 8) < 0.01
    assert 0 <= x and x + w <= SRC_W and 0 <= y and y + h <= SRC_H


def test_zoom_box_stays_inside_base():
    base = [196, 2, 606, 1076]
    x, y, w, h = zoom_box(base, (500.0, 400.0), 1.18)
    assert (w, h) == (512, 910)
    assert base[0] <= x and x + w <= base[0] + base[2]
    assert base[1] <= y and y + h <= base[1] + base[3]


def test_assign_tracks_two_people_and_drops_flicker():
    samples = [[Face(k / 5, RIGHT, 0.1), Face(k / 5, LEFT, 0.1)] for k in range(20)]
    samples[3].append(Face(0.6, (900.0, 500.0, 180.0, 180.0), 0.1))  # one-off false detection
    tracks = assign_tracks(samples, SRC_W)
    assert len(tracks) == 2
    assert tracks[0].median_box()[0] == LEFT[0]


def test_assign_tracks_drops_tiny_faces():
    samples = [[Face(k / 5, LEFT, 0.1), Face(k / 5, (1700.0, 900.0, 40.0, 40.0), 0.1)] for k in range(10)]
    assert len(assign_tracks(samples, SRC_W)) == 1


def test_plan_shot_without_faces_is_fit():
    assert plan_shot(0.0, 5.0, [], SRC_W, SRC_H, [])[0]["layout"] == "fit"


def test_plan_shot_single_person_fills_on_face():
    tracks = assign_tracks([[Face(k / 5, LEFT, 0.1)] for k in range(25)], SRC_W)
    segs = plan_shot(0.0, 5.0, tracks, SRC_W, SRC_H, [])
    assert len(segs) == 1 and segs[0]["layout"] == "fill"
    assert segs[0]["boxes"] == [fill_box(500.0, SRC_W, SRC_H)]
    assert segs[0]["face"] == [400, 300, 200, 200]


def test_plan_shot_switches_speaker_at_sentence_end():
    tracks = assign_tracks(two_person(8.0, lambda t: t < 4, lambda t: t >= 4), SRC_W)
    segs = plan_shot(0.0, 8.0, tracks, SRC_W, SRC_H, sentence_ends=[4.3])
    assert [s["layout"] for s in segs] == ["fill", "fill"]
    assert segs[0]["end"] == 4.3 and segs[1]["start"] == 4.3
    assert segs[0]["boxes"] == [fill_box(500.0, SRC_W, SRC_H)]
    assert segs[1]["boxes"] == [fill_box(1400.0, SRC_W, SRC_H)]


def test_plan_shot_short_interjection_does_not_switch():
    tracks = assign_tracks(two_person(7.0, lambda t: not 3 <= t < 4, lambda t: 3 <= t < 4), SRC_W)
    segs = plan_shot(0.0, 7.0, tracks, SRC_W, SRC_H, [])
    assert len(segs) == 1 and segs[0]["boxes"] == [fill_box(500.0, SRC_W, SRC_H)]


def test_plan_shot_back_and_forth_uses_split():
    tracks = assign_tracks(two_person(5.0, lambda t: True, lambda t: True), SRC_W)
    segs = plan_shot(0.0, 5.0, tracks, SRC_W, SRC_H, [])
    assert len(segs) == 1 and segs[0]["layout"] == "split" and len(segs[0]["boxes"]) == 2


def test_merge_short_shots():
    shots = [(0.0, 0.5), (0.5, 4.0), (4.0, 4.6), (4.6, 9.0)]
    assert merge_short_shots(shots) == [(0.0, 4.6), (4.6, 9.0)]


def test_plan_clip_plans_each_shot():
    samples = [(k / 5, [Face(k / 5, LEFT, 0.1)] if k < 15 else []) for k in range(30)]
    segs = plan_clip([(0.0, 3.0), (3.0, 6.0)], samples, SRC_W, SRC_H, [])
    assert [s["layout"] for s in segs] == ["fill", "fit"]
    assert (segs[1]["start"], segs[1]["end"]) == (3.0, 6.0)
