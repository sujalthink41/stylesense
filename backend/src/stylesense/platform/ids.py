import secrets
import time
import uuid

_RAND_A_BITS = 12
_RAND_B_BITS = 62


def new_id() -> uuid.UUID:
    """UUIDv7 (RFC 9562): 48-bit Unix ms timestamp + random bits, so ids sort by creation time.

    Generated client-side so SQLAlchemy can batch INSERTs instead of round-tripping per row
    to learn server-generated keys. (Python 3.14 adds uuid.uuid7; we're on 3.13.)
    """
    ms = time.time_ns() // 1_000_000
    rand_a = secrets.randbits(_RAND_A_BITS)
    rand_b = secrets.randbits(_RAND_B_BITS)
    value = (ms & (2**48 - 1)) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return uuid.UUID(int=value)
