"""Pure statistics helpers over Decimals (no database), so they are easy to test."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

CENT = Decimal("0.01")
# Peer groups smaller than this are too small to call anyone "unusual".
MIN_PEERS_FOR_OUTLIERS = 4


def percentile(sorted_values: Sequence[Decimal], fraction: Decimal | str) -> Decimal:
    """Linear interpolation between closest ranks (same as numpy's default)."""
    if not sorted_values:
        raise ValueError("percentile of an empty list")
    fraction = Decimal(fraction)
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    value = sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight
    return value.quantize(CENT)


@dataclass(frozen=True)
class Spread:
    count: int
    min: Decimal
    p25: Decimal
    median: Decimal
    p75: Decimal
    max: Decimal

    @property
    def low_fence(self) -> Decimal:
        return self.p25 - (self.p75 - self.p25) * Decimal("1.5")

    @property
    def high_fence(self) -> Decimal:
        return self.p75 + (self.p75 - self.p25) * Decimal("1.5")

    def is_outlier(self, value: Decimal) -> bool:
        if self.count < MIN_PEERS_FOR_OUTLIERS:
            return False
        return value < self.low_fence or value > self.high_fence


def spread(values: Sequence[Decimal]) -> Spread:
    ordered = sorted(values)
    return Spread(
        count=len(ordered),
        min=ordered[0].quantize(CENT),
        p25=percentile(ordered, "0.25"),
        median=percentile(ordered, "0.5"),
        p75=percentile(ordered, "0.75"),
        max=ordered[-1].quantize(CENT),
    )


def median(values: Sequence[Decimal]) -> Decimal:
    return percentile(sorted(values), "0.5")


def pct_diff(value: Decimal, reference: Decimal) -> Decimal:
    """(value - reference) / reference as a percentage with one decimal."""
    if reference == 0:
        return Decimal("0.0")
    return ((value - reference) / reference * 100).quantize(Decimal("0.1"))


def histogram(values: Sequence[Decimal], bins: int) -> list[tuple[Decimal, Decimal, int]]:
    """Equal-width bins from the lowest to the highest value: (start, end, count)."""
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [(low.quantize(CENT), high.quantize(CENT), len(values))]
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        index = min(int((value - low) / width), bins - 1)
        counts[index] += 1
    return [
        ((low + width * i).quantize(CENT), (low + width * (i + 1)).quantize(CENT), counts[i])
        for i in range(bins)
    ]
