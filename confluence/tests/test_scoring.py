from confluence.confluence_core.scoring import score_day, score_swing, score_hold


def test_score_day_basic():
    f = {"trend": 1, "level": 1, "trigger": 1, "rvol": 1, "volatility": 1, "catalyst_risk": 0}
    assert score_day(f) == 95


def test_score_swing_basic():
    f = {"htf_trend": 1, "base": 1, "break_retest": 1, "fundamentals": 1, "catalyst_risk": 0, "rr": 1}
    assert score_swing(f) == 100


def test_score_hold_basic():
    f = {"quality": 1, "earnings_durability": 1, "balance_sheet": 1, "valuation": 1, "tailwinds": 1, "dd_profile": 1}
    assert score_hold(f) == 100

