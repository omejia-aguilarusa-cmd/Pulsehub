from confluence.confluence_core.risk import position_size


def test_position_size():
    qty = position_size(10000.0, 1.0, entry=100.0, stop=99.0)
    assert round(qty, 2) == 100.0

