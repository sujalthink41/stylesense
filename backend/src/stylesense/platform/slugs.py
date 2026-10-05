import hashlib
import hmac
import secrets
import string

_ALPHABET = string.ascii_letters + string.digits
SLUG_LENGTH = 8  # 62**8 ≈ 2e14: unguessable for links we don't list anywhere


def new_slug(length: int = SLUG_LENGTH) -> str:
    """Short, random, URL-safe public id for share and poll links."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


class Pseudonymizer:
    """Keyed hashing for identifiers we must compare but never store (voter tokens, IPs).

    HMAC with a server-side key: a leaked table can't be reversed or brute-forced offline the
    way a plain hash of an IPv4 address can.
    """

    def __init__(self, key: bytes) -> None:
        self._key = key

    @classmethod
    def derive(cls, secret: str, purpose: str) -> "Pseudonymizer":
        # One deployment secret, a separate key per purpose.
        return cls(hmac.new(secret.encode(), purpose.encode(), hashlib.sha256).digest())

    def __call__(self, value: str) -> str:
        return hmac.new(self._key, value.encode(), hashlib.sha256).hexdigest()[:32]
