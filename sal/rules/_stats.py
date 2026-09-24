"""Online (streaming) mean/stdev via Welford's algorithm.

Lets each rule evaluate an observation against the baseline built from
everything *before* it, then fold that observation into the baseline for
next time - without re-scanning history on every event.
"""


class OnlineStats:
    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2

    @property
    def stdev(self) -> float:
        if self.n < 2:
            return 0.0
        return (self.m2 / (self.n - 1)) ** 0.5
