from __future__ import annotations

from typing import Any

from nacl.signing import SigningKey
from nacl.encoding import RawEncoder

from confluence.connectors.robinhood_crypto import RobinhoodCryptoClient as _RHC


def sign_ed25519(private_key_pem: bytes, message: bytes) -> bytes:
    # This is a simple signer; for official API, construct canonical request per docs.
    key = SigningKey.from_seed(private_key_pem[-32:], encoder=RawEncoder)
    sig = key.sign(message)
    return sig.signature


class RobinhoodCryptoClient(_RHC):
    pass


__all__ = ["RobinhoodCryptoClient", "sign_ed25519"]

