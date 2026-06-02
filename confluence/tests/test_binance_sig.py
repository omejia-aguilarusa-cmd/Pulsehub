import hmac, hashlib


def test_binance_hmac_signature():
    secret = b"testsecret"
    query = "symbol=BTCUSDT&side=BUY&type=LIMIT&timestamp=1710000000000"
    sig = hmac.new(secret, query.encode(), hashlib.sha256).hexdigest()
    assert len(sig) == 64

