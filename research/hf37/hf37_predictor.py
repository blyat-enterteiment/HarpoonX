"""Research-only causal pressure features and matured-label return forecasts.

Quotes/trades identify observed aggression, never the owner of an order. The
confidence calculation is a clustered, model-dependent estimate, not a guarantee.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import math
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray

Array: TypeAlias = NDArray[np.float64]
DAY_NS = 86_400_000_000_000


@dataclass(frozen=True)
class Trade:
    at_ns: int
    known_ns: int
    price: float
    size: float


@dataclass(frozen=True)
class Quote:
    at_ns: int
    known_ns: int
    bid: float
    ask: float
    bid_size: float
    ask_size: float

    def validate(self) -> None:
        if (
            not isinstance(self.at_ns, int)
            or not isinstance(self.known_ns, int)
            or not 0 < self.at_ns <= self.known_ns
        ):
            raise ValueError("INVALID_QUOTE_CLOCK")
        if not all(
            math.isfinite(x) for x in (self.bid, self.ask, self.bid_size, self.ask_size)
        ):
            raise ValueError("NONFINITE_QUOTE")
        if not 0 < self.bid < self.ask or min(self.bid_size, self.ask_size) < 0:
            raise ValueError("INVALID_QUOTE")


@dataclass(frozen=True)
class Pressure:
    available: bool
    score: float
    large_score: float
    threshold_usd: float
    classified: int
    unclassified: int
    large_events: int
    quote_spread_bps: float
    reason: str

    @property
    def feature(self) -> float:
        return 0.5 * (self.score + self.large_score)


def pressure_features(
    baseline: list[Trade],
    trades: list[Trade],
    quotes: list[Quote],
    window_start_ns: int,
    decision_ns: int,
    *,
    min_baseline: int = 50,
    min_classified: int = 10,
    min_coverage: float = 0.5,
    max_quote_age_ns: int = 2_000_000_000,
) -> Pressure:
    if not 0 < window_start_ns < decision_ns or max_quote_age_ns <= 0:
        raise ValueError("INVALID_FEATURE_CLOCK")
    if min_baseline < 2 or min_classified < 1 or not 0 <= min_coverage <= 1:
        raise ValueError("INVALID_FEATURE_CONFIGURATION")
    for t in baseline + trades:
        if (
            not isinstance(t.at_ns, int)
            or not isinstance(t.known_ns, int)
            or not 0 < t.at_ns <= t.known_ns <= decision_ns
        ):
            raise ValueError("NONCAUSAL_TRADE")
        if not all(math.isfinite(x) and x > 0 for x in (t.price, t.size)):
            raise ValueError("INVALID_TRADE")
    if any(t.known_ns >= window_start_ns for t in baseline):
        raise ValueError("BASELINE_NOT_STRICTLY_BEFORE_SIGNAL")
    if any(not window_start_ns <= t.at_ns <= decision_ns for t in trades):
        raise ValueError("TRADE_OUTSIDE_FEATURE_WINDOW")
    for q in quotes:
        q.validate()
        if q.known_ns > decision_ns:
            raise ValueError("FUTURE_QUOTE")
    unavailable = Pressure(False, 0, 0, 0, 0, len(trades), 0, 0, "INSUFFICIENT_TAPE")
    if len(baseline) < min_baseline or not trades or not quotes:
        return unavailable
    threshold = float(np.quantile([t.price * t.size for t in baseline], 0.9))
    ordered = sorted(quotes, key=lambda q: q.at_ns)
    stamps = [q.at_ns for q in ordered]
    signed = gross = large_signed = large_gross = 0.0
    classified = large_events = 0
    for t in sorted(trades, key=lambda t: t.at_ns):
        j = bisect_right(stamps, t.at_ns) - 1
        # A late newest quote must not hide a usable older causal quote.
        while j >= 0 and ordered[j].known_ns > t.known_ns:
            j -= 1
        if j < 0 or t.at_ns - ordered[j].at_ns > max_quote_age_ns:
            continue
        q = ordered[j]
        sign = 1 if t.price >= q.ask else -1 if t.price <= q.bid else 0
        if not sign:
            continue
        value = t.price * t.size
        signed += sign * value
        gross += value
        classified += 1
        if value >= threshold:
            large_signed += sign * value
            large_gross += value
            large_events += 1
    last = ordered[-1]
    spread = (last.ask - last.bid) / ((last.ask + last.bid) / 2) * 10_000
    enough = (
        classified >= min_classified
        and classified / len(trades) >= min_coverage
        and large_events > 0
        and decision_ns - last.at_ns <= max_quote_age_ns
    )
    return Pressure(
        enough,
        signed / gross if gross else 0,
        large_signed / large_gross if large_gross else 0,
        threshold,
        classified,
        len(trades) - classified,
        large_events,
        spread,
        "CAUSAL_PRESSURE_PROXY" if enough else "INSUFFICIENT_CLASSIFIED_EVIDENCE",
    )


@dataclass(frozen=True)
class Label:
    feature_ns: int
    end_ns: int
    known_ns: int
    symbol: str
    sector: str
    sector_feature: float
    pressure_feature: float
    gross_return: float
    is_etf: bool = False

    def validate(self) -> None:
        if not 0 < self.feature_ns < self.end_ns <= self.known_ns:
            raise ValueError("INVALID_LABEL_CLOCK")
        if self.end_ns - self.feature_ns > 3 * DAY_NS:
            raise ValueError("LABEL_HORIZON_OVER_72H")
        if (
            not all(
                math.isfinite(x)
                for x in (self.sector_feature, self.pressure_feature, self.gross_return)
            )
            or self.gross_return <= -1
        ):
            raise ValueError("INVALID_LABEL")
        if max(abs(self.sector_feature), abs(self.pressure_feature)) > 1:
            raise ValueError("UNSCALED_FEATURE")


@dataclass(frozen=True)
class Forecast:
    available: bool
    mean: float
    lower: float
    variance: float
    clusters: int
    observations: int

    @property
    def upper(self) -> float:
        return 2 * self.mean - self.lower


@dataclass
class ReturnModel:
    beta: Array
    coefficient_covariance: Array
    residual_variance: float
    clusters: int
    observations: int
    whale: bool
    trained_through_ns: int
    z: float = 2.0
    bias_buffer: float = 0.0005
    min_clusters: int = 40

    def predict(self, sector: float, pressure: float, decision_ns: int) -> Forecast:
        if self.trained_through_ns > decision_ns or not all(
            math.isfinite(v) and abs(v) <= 1 for v in (sector, pressure)
        ):
            raise ValueError("NONCAUSAL_OR_INVALID_PREDICTION")
        x = np.array([1, sector, pressure] if self.whale else [1, sector], dtype=float)
        uncertainty = max(0.0, float(x @ self.coefficient_covariance @ x))
        mean = float(x @ self.beta)
        lower = mean - self.z * math.sqrt(uncertainty) - self.bias_buffer
        return Forecast(
            self.clusters >= self.min_clusters,
            mean,
            lower,
            max(1e-8, self.residual_variance + uncertainty),
            self.clusters,
            self.observations,
        )


def fit_return_model(
    labels: list[Label],
    decision_ns: int,
    *,
    whale: bool,
    lookback_days: int = 120,
    min_clusters: int = 40,
) -> ReturnModel:
    if decision_ns <= 0 or lookback_days < 1 or min_clusters < 4:
        raise ValueError("INVALID_MODEL_CONFIGURATION")
    for label in labels:
        label.validate()
    eligible = [
        label
        for label in labels
        if label.known_ns <= decision_ns
        and label.feature_ns >= decision_ns - lookback_days * DAY_NS
        and label.is_etf != whale
    ]
    dim = 3 if whale else 2
    if not eligible:
        return ReturnModel(
            np.zeros(dim), np.eye(dim), 1.0, 0, 0, whale, 0, min_clusters=min_clusters
        )
    x = np.array(
        [
            [1, label.sector_feature, label.pressure_feature]
            if whale
            else [1, label.sector_feature]
            for label in eligible
        ],
        dtype=float,
    )
    y = np.array([label.gross_return for label in eligible], dtype=float)
    gram = x.T @ x + np.diag([1.0] + [10.0] * (dim - 1))
    inv = np.linalg.solve(gram, np.eye(dim))
    beta = inv @ x.T @ y
    residual = y - x @ beta
    groups: dict[int, list[int]] = {}
    for i, label in enumerate(eligible):
        groups.setdefault(label.feature_ns, []).append(i)
    meat = np.zeros((dim, dim))
    for indices in groups.values():
        gradient = x[indices].T @ residual[indices]
        meat += np.outer(gradient, gradient)
    n = len(groups)
    cov = inv @ meat @ inv * (n / (n - 1) if n > 1 else 1)
    return ReturnModel(
        beta,
        cov,
        max(1e-8, float(np.mean(residual**2))),
        n,
        len(eligible),
        whale,
        max(label.known_ns for label in eligible),
        min_clusters=min_clusters,
    )


def shrunk_covariance(panel: list[list[float]], assets: int) -> Array:
    if assets < 1 or len(panel) < 2:
        return np.eye(assets) * 0.0004
    matrix = np.asarray(panel, dtype=float)
    if matrix.shape != (len(panel), assets) or not np.isfinite(matrix).all():
        raise ValueError("INVALID_RETURN_PANEL")
    empirical = np.atleast_2d(np.cov(matrix, rowvar=False, ddof=1))
    return 0.5 * empirical + 0.5 * np.diag(np.diag(empirical)) + np.eye(assets) * 1e-8
