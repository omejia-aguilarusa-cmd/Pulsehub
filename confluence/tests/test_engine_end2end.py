from confluence.confluence_core.confluence_engine import make_strict_signal


def test_engine_signal_gate_passes():
    sig = make_strict_signal(
        ticker="AAPL",
        market="equity",
        style="day",
        entry=195.40,
        stop=192.80,
        targets=[199.5, 202.0],
        why=["Breakout"],
        rr=2.7,
        prob_success=0.62,
        score_inputs={"trend": 1, "level": 1, "trigger": 1, "rvol": 1, "volatility": 1, "catalyst_risk": 0},
        citations=["https://example.com/q"],
    )
    assert sig is not None
    assert sig.score >= 70

