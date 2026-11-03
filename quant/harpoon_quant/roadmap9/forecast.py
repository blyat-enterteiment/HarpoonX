"""Causal clock features and fixed ridge forecasts for offline roadmap research.

Historical bar availability is inherited from the admitted dataset. It is a
modelled timestamp, not an original market-receipt timestamp. No broker calls.
"""

from __future__ import annotations

import hashlib
import json
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any

import numpy as np

HOUR = 3_600_000
BAR = 300_000
FEATURES = (
    "opening_return",
    "sector_relative_return",
    "gap_vol",
    "volatility",
    "previous_overnight",
    "previous_intraday",
    "session_fraction",
)
HORIZONS = (24, 48, 72)


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class ClockPanel:
    """Index known bars and received calendar; never backfill missing observations."""

    def __init__(self, data: dict[str, Any]):
        require(data.get("schema") == "HARPOON-ULTIMATE-DATA-1", "CLOCK_DATA_SCHEMA")
        self.data = data
        self.sessions = data["sessions"]
        self.opens = [s["open"] for s in self.sessions]
        require(all(a < b for a, b in zip(self.opens, self.opens[1:])), "SESSION_ORDER")
        self.series = {s["symbol"]: s["bars"] for s in data["series"]}
        require(
            all(s in self.series for s in ("AAPL", "MSFT", "XLK")), "CLOCK_UNIVERSE"
        )
        self.times = {s: [b["t"] for b in bars] for s, bars in self.series.items()}
        self.arrivals = {
            s: [b["availableAt"] for b in bars] for s, bars in self.series.items()
        }
        for symbol, bars in self.series.items():
            require(
                all(a < b for a, b in zip(self.times[symbol], self.times[symbol][1:])),
                "BAR_ORDER",
            )
            require(
                all(
                    a <= b
                    for a, b in zip(self.arrivals[symbol], self.arrivals[symbol][1:])
                ),
                "ARRIVAL_ORDER",
            )
            require(
                all(
                    b["end"] == b["t"] + BAR
                    and b["availableAt"] >= b["end"]
                    and 0
                    < b["l"]
                    <= min(b["o"], b["c"])
                    <= max(b["o"], b["c"])
                    <= b["h"]
                    and all(math.isfinite(b[k]) for k in ("o", "h", "l", "c", "v"))
                    for b in bars
                ),
                "BAR_CONTRACT",
            )
        self.daily: dict[str, list[dict[str, Any] | None]] = {}
        for symbol in self.series:
            days: list[dict[str, Any] | None] = []
            for session in self.sessions:
                bars = self.between(symbol, session["open"], session["close"])
                if not bars:
                    days.append(None)
                    continue
                require(
                    len(bars) == (session["close"] - session["open"]) // BAR,
                    "INCOMPLETE_SESSION",
                )
                days.append(
                    {
                        "o": bars[0]["o"],
                        "c": bars[-1]["c"],
                        "h": max(b["h"] for b in bars),
                        "l": min(b["l"] for b in bars),
                        "available_at": bars[-1]["availableAt"],
                    }
                )
            self.daily[symbol] = days

    def between(self, symbol: str, start: int, end: int) -> list[dict[str, Any]]:
        times = self.times[symbol]
        return self.series[symbol][bisect_left(times, start) : bisect_left(times, end)]

    def latest(self, symbol: str, at: int) -> dict[str, Any] | None:
        index = bisect_right(self.arrivals[symbol], at) - 1
        return None if index < 0 else self.series[symbol][index]

    def at(self, symbol: str, at: int) -> dict[str, Any] | None:
        index = bisect_left(self.times[symbol], at)
        return (
            self.series[symbol][index]
            if index < len(self.times[symbol]) and self.times[symbol][index] == at
            else None
        )

    def deadline(self, decision: int, hours: int) -> int | None:
        require(hours in HORIZONS, "REGISTERED_HORIZON")
        end = decision + hours * HOUR
        if not self.sessions or self.sessions[-1]["close"] < end:
            return None
        candidates = [s for s in self.sessions if s["open"] <= end]
        if not candidates:
            return None
        session = candidates[-1]
        # The final complete five-minute bar is the last executable open.
        exit_at = min(end, session["close"] - 2 * BAR)
        return session["open"] + ((exit_at - session["open"]) // BAR) * BAR

    def features(self, symbol: str, at: int) -> dict[str, Any] | None:
        i = bisect_right(self.opens, at) - 1
        if i < 15 or not self.opens[i] <= at < self.sessions[i]["close"]:
            return None
        session = self.sessions[i]
        a, sector = self.latest(symbol, at), self.latest("XLK", at)
        if (
            a is None
            or sector is None
            or a["t"] != sector["t"]
            or a["t"] < session["open"]
        ):
            return None
        if at - a["availableAt"] > BAR or at - sector["availableAt"] > BAR:
            return None
        # No announcement time is fabricated for the retained XLK split.
        if any(
            e["symbol"] in (symbol, "XLK")
            and self.opens[i - 1] <= e["at"] <= at
            and (not isinstance(e.get("knownAt"), int) or e["knownAt"] > at)
            for e in self.data.get("splitEvents", [])
        ):
            return None
        if any(
            e["symbol"] == symbol and self.opens[i - 15] <= e["at"] <= at
            for e in self.data.get("splitEvents", [])
        ):
            return None
        previous = self.daily[symbol][i - 1]
        before = self.daily[symbol][i - 2]
        if previous is None or before is None or previous["available_at"] > at:
            return None
        lookback = self.daily[symbol][i - 15 : i]
        if any(d is None for d in lookback):
            return None
        assert all(d is not None for d in lookback)
        returns = np.log(
            np.array([d["c"] for d in lookback if d is not None][1:])
            / np.array([d["c"] for d in lookback if d is not None][:-1])
        )
        volatility = max(float(np.std(returns, ddof=1)), 1e-4)
        first = self.at(symbol, session["open"])
        first_sector = self.at("XLK", session["open"])
        if (
            first is None
            or first_sector is None
            or max(first["availableAt"], first_sector["availableAt"]) > at
        ):
            return None
        intraday = math.log(a["c"] / first["o"])
        relative = intraday - math.log(sector["c"] / first_sector["o"])
        gap = math.log(first["o"] / previous["c"])
        overnight = math.log(previous["o"] / before["c"])
        previous_intraday = math.log(previous["c"] / previous["o"])
        identity = math.log(previous["c"] / before["c"])
        require(
            abs(identity - overnight - previous_intraday) < 1e-12, "LOG_DECOMPOSITION"
        )
        tr = []
        for j in range(i - 14, i):
            d, prior = self.daily[symbol][j], self.daily[symbol][j - 1]
            assert d is not None and prior is not None
            tr.append(
                max(d["h"] - d["l"], abs(d["h"] - prior["c"]), abs(d["l"] - prior["c"]))
            )
        vector = [
            intraday,
            relative,
            gap / volatility,
            volatility,
            overnight,
            previous_intraday,
            (at - session["open"]) / (session["close"] - session["open"]),
        ]
        require(all(math.isfinite(x) for x in vector), "FEATURE_FINITE")
        return {
            "symbol": symbol,
            "session": session["date"],
            "session_index": i,
            "session_minute": (at - session["open"] - 1000) // 60_000,
            "decision_at": at,
            "available_at": max(
                a["availableAt"], sector["availableAt"], previous["available_at"]
            ),
            "planned_entry_at": session["open"]
            + math.ceil((at - session["open"]) / BAR) * BAR,
            "x": vector,
            "price": a["c"],
            "gap": gap,
            "opening_return": intraday,
            "sector_relative_return": relative,
            "stop_distance": max(float(np.mean(tr)), 0.02),
            "decomposition_residual": identity - overnight - previous_intraday,
        }

    def rows(self) -> list[dict[str, Any]]:
        result = []
        for session in self.sessions:
            for minute in (60, 120, 180, 240, 300, 360):
                at = session["open"] + minute * 60_000 + 1000
                if at + BAR >= session["close"]:
                    continue
                for symbol in ("AAPL", "MSFT"):
                    row = self.features(symbol, at)
                    if row is None:
                        continue
                    entry = self.at(symbol, row["planned_entry_at"])
                    if entry is None:
                        continue
                    labels = {}
                    for horizon in HORIZONS:
                        exit_at = self.deadline(at, horizon)
                        exit_bar = None if exit_at is None else self.at(symbol, exit_at)
                        split_crossing = any(
                            e["symbol"] == symbol
                            and row["planned_entry_at"] < e["at"] <= (exit_at or 0)
                            for e in self.data.get("splitEvents", [])
                        )
                        if (
                            exit_bar is not None
                            and exit_at > row["planned_entry_at"]
                            and not split_crossing
                        ):
                            total = math.log(exit_bar["o"] / entry["o"])
                            overnight = 0.0
                            identified = True
                            for j, future in enumerate(self.sessions):
                                if (
                                    not row["planned_entry_at"]
                                    < future["open"]
                                    <= exit_at
                                ):
                                    continue
                                today, prior = (
                                    self.daily[symbol][j],
                                    self.daily[symbol][j - 1],
                                )
                                if j == 0 or today is None or prior is None:
                                    identified = False
                                    break
                                overnight += math.log(today["o"] / prior["c"])
                            if identified:
                                labels[str(horizon)] = {
                                    "value": total,
                                    "overnight": overnight,
                                    "intraday": total - overnight,
                                    "known_at": exit_bar["availableAt"],
                                    "exit_at": exit_at,
                                }
                    result.append({**row, "labels": labels})
        return result


@dataclass(frozen=True)
class RidgeModel:
    """Fixed lambda ridge, daily-cluster HAC uncertainty of the conditional mean."""

    asof: int
    horizon: int
    columns: tuple[int, ...]
    location: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    coefficient_covariance: np.ndarray
    sample_count: int
    session_count: int
    latest_label_at: int
    residual_rmse: float
    overnight_coefficients: np.ndarray
    intraday_coefficients: np.ndarray
    calibration: dict[str, Any]

    def predict(self, row: dict[str, Any]) -> dict[str, float | int]:
        require(self.calibration["pass"], "CALIBRATION_REFERENCE_FAILURE")
        require(row["available_at"] <= row["decision_at"], "FUTURE_FEATURE")
        require(self.asof <= row["decision_at"], "FUTURE_MODEL")
        require(row["decision_at"] - self.asof <= 168 * HOUR, "STALE_MODEL")
        require(row["decision_at"] - self.latest_label_at <= 168 * HOUR, "STALE_LABELS")
        x = np.array(row["x"], dtype=float)[list(self.columns)]
        z = (x - self.location) / self.scale
        require(np.isfinite(z).all() and np.max(np.abs(z)) <= 8, "FEATURE_DRIFT")
        design = np.r_[1.0, z]
        mean = float(design @ self.coefficients)
        uncertainty = math.sqrt(
            max(0.0, float(design @ self.coefficient_covariance @ design))
        )
        overnight = float(design @ self.overnight_coefficients)
        intraday = float(design @ self.intraday_coefficients)
        require(abs(mean - overnight - intraday) < 1e-10, "FORECAST_COMPONENT_IDENTITY")
        return {
            "mean": mean,
            "overnight_mean": overnight,
            "intraday_mean": intraday,
            "mean_se": uncertainty,
            "lower": mean - 1.645 * uncertainty,
            "horizon_hours": self.horizon,
            "model_asof": self.asof,
            "latest_label_at": self.latest_label_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "asof": self.asof,
            "horizon": self.horizon,
            "columns": list(self.columns),
            "location": self.location.tolist(),
            "scale": self.scale.tolist(),
            "coefficients": self.coefficients.tolist(),
            "coefficient_covariance": self.coefficient_covariance.tolist(),
            "sample_count": self.sample_count,
            "session_count": self.session_count,
            "latest_label_at": self.latest_label_at,
            "residual_rmse": self.residual_rmse,
            "overnight_coefficients": self.overnight_coefficients.tolist(),
            "intraday_coefficients": self.intraday_coefficients.tolist(),
            "calibration": self.calibration,
            "component_uncertainty": "HAC of total captures dependence; marginal errors are not summed as independent",
            "regularization": 10.0,
            "hac_session_lags": 5,
            "origin": "HISTORICAL_MODELED",
        }


def fit_ridge(
    rows: list[dict[str, Any]], asof: int, horizon: int, *, clock: bool = True
) -> RidgeModel:
    require(horizon in HORIZONS, "REGISTERED_HORIZON")
    eligible = [
        r
        for r in rows
        if r["decision_at"] < asof
        and str(horizon) in r["labels"]
        and r["labels"][str(horizon)]["known_at"] <= asof
        and r["available_at"] <= r["decision_at"]
    ]
    days = sorted({r["session"] for r in eligible})[-126:]
    require(len(days) >= 90, "INSUFFICIENT_MATURED_TRAINING_SESSIONS")
    dayset = set(days)
    train = [r for r in eligible if r["session"] in dayset]
    columns = tuple(range(len(FEATURES))) if clock else (0, 1, 2, 3)
    x = np.array([r["x"] for r in train], dtype=float)[:, list(columns)]
    y = np.array([r["labels"][str(horizon)]["value"] for r in train])
    location = np.mean(x, axis=0)
    scale = np.maximum(np.std(x, axis=0, ddof=1), 1e-8)
    design = np.column_stack([np.ones(len(x)), (x - location) / scale])
    penalty = np.eye(design.shape[1]) * 10.0
    penalty[0, 0] = 0
    inverse = np.linalg.inv(design.T @ design + penalty)
    beta = inverse @ design.T @ y
    overnight_beta = (
        inverse
        @ design.T
        @ np.array([r["labels"][str(horizon)]["overnight"] for r in train])
    )
    intraday_beta = (
        inverse
        @ design.T
        @ np.array([r["labels"][str(horizon)]["intraday"] for r in train])
    )
    residual = y - design @ beta
    # Calibration remains entirely inside matured TRAIN, with an explicit purge
    # between the preceding fit and its final twenty-session validation slice.
    calibration_days = set(days[-20:])
    calibration_rows = [r for r in train if r["session"] in calibration_days]
    calibration_cut = min(r["decision_at"] for r in calibration_rows)
    earlier = [
        r
        for r in train
        if r["session"] not in calibration_days
        and r["labels"][str(horizon)]["known_at"] <= calibration_cut
    ]
    require(
        len({r["session"] for r in earlier}) >= 60, "INSUFFICIENT_CALIBRATION_TRAIN"
    )
    early_x = np.array([r["x"] for r in earlier])[:, list(columns)]
    early_mean = early_x.mean(axis=0)
    early_scale = np.maximum(early_x.std(axis=0, ddof=1), 1e-8)
    early_design = np.column_stack(
        [np.ones(len(earlier)), (early_x - early_mean) / early_scale]
    )
    early_y = np.array([r["labels"][str(horizon)]["value"] for r in earlier])
    early_beta = np.linalg.solve(
        early_design.T @ early_design + penalty, early_design.T @ early_y
    )
    calibration_x = np.array([r["x"] for r in calibration_rows])[:, list(columns)]
    calibration_design = np.column_stack(
        [np.ones(len(calibration_rows)), (calibration_x - early_mean) / early_scale]
    )
    calibration_y = np.array(
        [r["labels"][str(horizon)]["value"] for r in calibration_rows]
    )
    calibration_mse = float(
        np.mean((calibration_y - calibration_design @ early_beta) ** 2)
    )
    reference_mse = float(np.mean(calibration_y**2))
    calibration = {
        "train_sessions": len({r["session"] for r in earlier}),
        "calibration_sessions": 20,
        "sample_count": len(calibration_rows),
        "fit_labels_known_before": calibration_cut,
        "maximum_label_known_at": max(
            r["labels"][str(horizon)]["known_at"] for r in calibration_rows
        ),
        "mse": calibration_mse,
        "zero_reference_mse": reference_mse,
        "tolerance_ratio": 1.25,
        "pass": calibration_mse <= 1.25 * max(reference_mse, 1e-16),
        "scope": "PURGED_TRAIN_ONLY_PREDICTIVE_GUARD_NOT_ECONOMIC_APPROVAL",
    }
    scores = np.array(
        [
            np.sum(
                design[[i for i, r in enumerate(train) if r["session"] == day]]
                * residual[
                    [i for i, r in enumerate(train) if r["session"] == day], None
                ],
                axis=0,
            )
            for day in days
        ]
    )
    meat = scores.T @ scores
    for lag in range(1, min(5, len(scores) - 1) + 1):
        cross = scores[lag:].T @ scores[:-lag]
        meat += (1 - lag / 6) * (cross + cross.T)
    covariance = inverse @ meat @ inverse
    covariance = (covariance + covariance.T) / 2
    eigen, vectors = np.linalg.eigh(covariance)
    require(eigen.min() > -1e-8, "HAC_COVARIANCE_INVALID")
    covariance = (vectors * np.maximum(eigen, 0)) @ vectors.T
    latest = max(r["labels"][str(horizon)]["known_at"] for r in train)
    return RidgeModel(
        asof,
        horizon,
        columns,
        location,
        scale,
        beta,
        covariance,
        len(train),
        len(days),
        latest,
        float(np.sqrt(np.mean(residual**2))),
        overnight_beta,
        intraday_beta,
        calibration,
    )
