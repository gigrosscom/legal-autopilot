"""Lawyer rating by proven results.

Design goals (the formula is public so lawyers and clients can trust it):
  * only verified platform cases count (outcomes recorded by the engine, not self-reported);
  * small samples are pulled towards the platform average (Bayesian smoothing),
    so 3 wins out of 3 does not beat 180 out of 220;
  * results are compared to the platform baseline *for the same case category*,
    so taking only easy cases does not inflate the score;
  * reliability (milestones met on time) and money actually recovered matter,
    not only "won/lost";
  * reviews count only from completed deals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

PRIOR_CASES = 30  # weight of the platform average, in "virtual cases"
PRIOR_RECOVERY = 0.6  # platform-wide share of claimed money recovered
PRIOR_REVIEWS = 5
PRIOR_REVIEW_SCORE = 4.0

WEIGHTS = {"effectiveness": 0.45, "reliability": 0.20, "recovery": 0.20, "reviews": 0.15}


@dataclass
class CategoryStats:
    category: str
    cases: int
    won: int
    partial: int
    claimed: float = 0.0  # total amount claimed in these cases
    recovered: float = 0.0  # total amount actually recovered


@dataclass
class LawyerStats:
    categories: list[CategoryStats]
    milestones_total: int = 0
    milestones_on_time: int = 0
    reviews_count: int = 0
    reviews_avg: float = 0.0


@dataclass
class Score:
    total: int  # 0..100
    effectiveness: float  # smoothed success rate, 0..1
    vs_baseline: float  # effectiveness minus platform baseline, in percentage points
    reliability: float  # smoothed share of milestones met on time
    recovery: float  # recovered / claimed
    reviews: float  # smoothed 1..5
    verified_cases: int
    confidence: str  # low | medium | high

    def to_dict(self) -> dict:
        return asdict(self)


def smoothed(successes: float, n: int, prior_rate: float, prior_n: int) -> float:
    return (successes + prior_rate * prior_n) / (n + prior_n)


def score(stats: LawyerStats, baseline: dict[str, float], baseline_reliability: float = 0.85) -> Score:
    """``baseline``: platform success rate per category (won + 0.5·partial) / cases."""
    n = sum(c.cases for c in stats.categories)
    success = sum(c.won + 0.5 * c.partial for c in stats.categories)
    # expected success if this lawyer were exactly average on the same mix of categories
    expected = sum(c.cases * baseline.get(c.category, 0.5) for c in stats.categories)
    base_rate = expected / n if n else 0.5
    eff = smoothed(success, n, base_rate, PRIOR_CASES)
    lift = eff - base_rate

    rel = smoothed(stats.milestones_on_time, stats.milestones_total, baseline_reliability, PRIOR_CASES)
    claimed = sum(c.claimed for c in stats.categories)
    raw_recovery = (sum(c.recovered for c in stats.categories) / claimed) if claimed else PRIOR_RECOVERY
    recovery = smoothed(raw_recovery * n, n, PRIOR_RECOVERY, PRIOR_CASES)
    reviews = ((stats.reviews_avg * stats.reviews_count + PRIOR_REVIEW_SCORE * PRIOR_REVIEWS)
               / (stats.reviews_count + PRIOR_REVIEWS))

    # effectiveness is scored relative to the baseline: average lawyer → 50, +25 p.p. → 100
    eff_points = max(0.0, min(1.0, 0.5 + 2 * lift))
    total = (WEIGHTS["effectiveness"] * eff_points
             + WEIGHTS["reliability"] * rel
             + WEIGHTS["recovery"] * min(1.0, recovery)
             + WEIGHTS["reviews"] * (reviews - 1) / 4)
    confidence = "high" if n >= 50 else "medium" if n >= 15 else "low"
    return Score(total=round(100 * total), effectiveness=round(eff, 3), vs_baseline=round(100 * lift, 1),
                 reliability=round(rel, 3), recovery=round(recovery, 3), reviews=round(reviews, 2),
                 verified_cases=n, confidence=confidence)
