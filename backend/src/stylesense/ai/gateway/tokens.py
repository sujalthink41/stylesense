"""Pre-flight token estimate used only as a safety cap; billing uses the provider's counts.

Deliberately conservative (~3 chars/token vs the usual ~4) and tokenizer-free, so it works for
any provider and needs no downloaded vocabulary files.
"""

import math
from collections.abc import Iterable

from stylesense.ai.gateway.types import Message

_CHARS_PER_TOKEN = 3
_PER_MESSAGE_OVERHEAD = 4
# A low-detail image costs ~85 tokens on OpenAI, more on others: stay on the safe side.
IMAGE_TOKENS = 1_600


def estimate_tokens(messages: Iterable[Message]) -> int:
    return sum(
        math.ceil(len(m.content) / _CHARS_PER_TOKEN)
        + _PER_MESSAGE_OVERHEAD
        + IMAGE_TOKENS * len(m.images)
        for m in messages
    )
