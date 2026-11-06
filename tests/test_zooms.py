from clipper.zooms import plan_zooms, toggle_times

CFG = {"zoom": {"enabled": True, "scale": 1.18, "min_gap": 4.0, "max_gap": 7.0}}
FILL = [{"start": 0.0, "end": 20.0, "layout": "fill"}]


def test_toggles_follow_anchors_within_gap_limits():
    assert toggle_times([2, 4, 6, 8, 10, 12, 14, 16, 18], 20.0, 4.0, 7.0) == [4, 8, 12, 16]


def test_toggles_forced_when_no_anchor():
    assert toggle_times([], 20.0, 4.0, 7.0) == [7.0, 14.0]


def test_zoom_in_out_pairs():
    zooms = plan_zooms(FILL, [2, 4, 6, 8, 10, 12, 14, 16, 18], 20.0, CFG)
    assert [(z["start"], z["end"]) for z in zooms] == [(4, 8), (12, 16)]
    assert all(z["scale"] == 1.18 for z in zooms)


def test_zoom_resets_at_shot_boundary():
    segs = [{"start": 0.0, "end": 10.0, "layout": "fill"}, {"start": 10.0, "end": 20.0, "layout": "fill"}]
    assert [(z["start"], z["end"]) for z in plan_zooms(segs, [6.0], 20.0, CFG)] == [(6.0, 10.0)]


def test_no_zoom_in_split_or_fit_or_when_disabled():
    split = [{"start": 0.0, "end": 20.0, "layout": "split"}]
    assert plan_zooms(split, [4.0, 8.0], 20.0, CFG) == []
    off = {"zoom": {**CFG["zoom"], "enabled": False}}
    assert plan_zooms(FILL, [4.0, 8.0], 20.0, off) == []


def test_non_positive_gaps_do_not_hang():
    toggles = toggle_times([5, 10], 30, 0.0, 7.0)
    assert toggles and all(b > a for a, b in zip(toggles, toggles[1:]))
    toggles = toggle_times([], 30, -1.0, 0.0)
    assert toggles and all(b > a for a, b in zip(toggles, toggles[1:]))
