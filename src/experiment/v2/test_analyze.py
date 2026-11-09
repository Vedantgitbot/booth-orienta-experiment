"""Hand-checked tests for analyze.py:  python src/experiment/v2/test_analyze.py"""
import analyze as a


def mk(sid, claim_fail, action_risk, b, o):
    return {"scenario_id": sid, "claim_fail": claim_fail, "action_risk": action_risk, "b": b, "o": o}


ITEMS = [
    mk("s1", True, False, True, False),    # claim-only, BOOTH catches
    mk("s1", True, False, False, False),   # claim-only, nobody catches
    mk("s2", False, True, False, True),    # action-only, Orienta catches
    mk("s2", False, True, True, True),     # action-only, both catch
    mk("s3", True, True, True, False),     # both failure types, BOOTH catches
    mk("s4", False, False, False, False),  # clean
    mk("s5", False, False, True, False),   # clean, BOOTH false alarm
]


def rec(flagged=True, inconclusive=False, checker_failed=False, error=None):
    return {"flagged": flagged, "inconclusive": inconclusive, "checker_failed": checker_failed, "error": error}


def test_counts():
    assert a.count(ITEMS, *a.M["booth_recall"]) == (2, 3)
    assert a.count(ITEMS, *a.M["booth_false_flag"]) == (2, 4)
    assert a.count(ITEMS, *a.M["orienta_recall"]) == (2, 3)
    assert a.count(ITEMS, *a.M["claim_only__booth"]) == (1, 2)
    assert a.count(ITEMS, *a.M["claim_only__orienta"]) == (0, 2)
    assert a.count(ITEMS, *a.M["action_only__orienta"]) == (2, 2)
    assert a.count(ITEMS, *a.M["action_only__booth"]) == (1, 2)
    assert a.count(ITEMS, *a.M["union_recall"]) == (4, 5)
    assert a.count(ITEMS, *a.M["union_false_alarm"]) == (1, 2)
    assert a.count(ITEMS, *a.M["booth_recall_any"]) == (3, 5)
    assert a.count(ITEMS, *a.M["orienta_recall_any"]) == (2, 5)


def test_differences():
    d = a.diffs(lambda m: a.frac(ITEMS, m))
    assert abs(d["H1_claim_only_booth_minus_orienta"] - 0.5) < 1e-9
    assert abs(d["H2_action_only_orienta_minus_booth"] - 0.5) < 1e-9
    assert abs(d["H3_union_minus_best_single"] - (4 / 5 - 3 / 5)) < 1e-9


def test_empty_denominator_is_none():
    assert a.frac([mk("s", False, False, False, False)], "booth_recall") is None
    d = a.diffs(lambda m: None)
    assert all(v is None for v in d.values())


def test_booth_rules():
    r = {"m1": rec(True), "m2": rec(False)}
    assert a.booth_verdict(r, "any") is True
    assert a.booth_verdict(r, "all") is False
    assert a.booth_verdict(r, "judge:m2") is False
    assert a.booth_verdict({"m1": rec(False), "m2": rec(False)}, "any") is False
    assert a.booth_verdict({"m1": rec(True), "m2": rec(True)}, "all") is True
    assert a.booth_verdict({"m1": rec(True), "m2": rec(inconclusive=True)}, "any") is True
    assert a.booth_verdict({"m1": rec(False), "m2": rec(inconclusive=True)}, "any") is None
    assert a.booth_verdict({"m1": rec(False), "m2": rec(error="x")}, "all") is False
    assert a.booth_verdict({"m1": rec(checker_failed=True)}, "judge:m1") is None
    assert a.booth_verdict({}, "any") is None


def test_quadrant():
    assert [a.quadrant(i) for i in ITEMS[:5]] == ["claim_only", "claim_only", "action_only", "action_only", "both"]
    assert a.quadrant(ITEMS[5]) == "neither"


def test_wilson():
    lo, hi = a.wilson(5, 10)
    assert 0.23 < lo < 0.24 and 0.76 < hi < 0.77
    assert a.wilson(0, 0) is None


def test_bootstrap_is_deterministic_and_sane():
    items = [mk(f"s{n}", True, False, n % 2 == 0, False) for n in range(12)] * 3
    x, y = a.bootstrap(items, n_boot=300), a.bootstrap(items, n_boot=300)
    assert x == y
    lo, hi = x["booth_recall"]
    assert 0 <= lo <= 0.5 <= hi <= 1
    assert x["H1_claim_only_booth_minus_orienta"][0] > 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} tests passed")