import math
from dataclasses import dataclass
from decimal import Decimal

from stylesense.ai.gateway.types import Usage


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD per million tokens, which conveniently equals micro-USD per token."""

    input_usd_per_mtok: Decimal
    cached_input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal

    def cost_micro_usd(self, usage: Usage) -> int:
        cached = min(max(usage.cached_input_tokens, 0), max(usage.input_tokens, 0))
        fresh = max(usage.input_tokens, 0) - cached
        total = (
            fresh * self.input_usd_per_mtok
            + cached * self.cached_input_usd_per_mtok
            + max(usage.output_tokens, 0) * self.output_usd_per_mtok
        )
        # Integer micro-dollars (like paise for money); round up so budgets never undercount.
        return math.ceil(total)
