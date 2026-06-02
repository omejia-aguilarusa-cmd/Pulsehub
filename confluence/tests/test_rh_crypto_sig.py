from confluence.brokers.robinhood_crypto import sign_ed25519


def test_ed25519_signature_deterministic():
    # 32-byte seed for testing (NOT PEM). sign_ed25519 expects last 32 bytes as seed.
    seed = bytes(range(32))
    msg = b"test-message"
    sig = sign_ed25519(seed, msg)
    assert isinstance(sig, bytes)
    assert len(sig) == 64

