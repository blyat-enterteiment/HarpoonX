"""Contracts for technical predictors at calibration and inference boundaries."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Any


def declared_order(row: Mapping[str, Any], expected: Sequence[str]) -> None:
    # Historical positional panels have a fixed, documented column order.
    if "feature_names" in row and row["feature_names"] != list(expected):
        raise ValueError("TECHNICAL_FEATURE_ORDER")


def named_subset(names: Any, allowed: Collection[str]) -> None:
    if (
        not isinstance(names, list)
        or not names
        or not all(isinstance(name, str) and name in allowed for name in names)
        or len(names) != len(set(names))
    ):
        raise ValueError("UNREGISTERED_TECHNICAL_FEATURE")


def path_fields(fields: Any, symbols: list[str], origin: str) -> None:
    indicators = (
        "return1",
        "momentum5",
        "vol21",
        "trend20_z",
        "macd12_30_9_hist_z",
        "macd_hist_change_z",
        "rsi14_centered",
        "stochastic14_3_3_diff",
    )
    allowed = {
        f"{symbol.replace('/', '_')}_{name}"
        for symbol in symbols
        for name in indicators
    }
    if origin == "SYNTHETIC_ENGINEERING_ONLY":
        allowed.update({"SYNTHETIC_VOL", "SYNTHETIC_MOM"})
        allowed.update(
            f"{s}_{name}"
            for s in symbols
            for name in ("PREVIOUS_RETURN", "PREVIOUS8_VOL")
        )
    named_subset(fields, allowed)


def regime_fields(fields: Any) -> None:
    names = {"largest_eigen_share", "effective_rank", "mean_corr", "pc1"}
    if isinstance(fields, list):
        for field in fields:
            match = (
                re.fullmatch(
                    r"(?:mean|dispersion)_w([0-9]{1,3})_lag(-?[0-9]{1,2})", field
                )
                if isinstance(field, str)
                else None
            )
            if match and 16 <= int(match[1]) <= 512 and abs(int(match[2])) <= 12:
                names.add(field)
    named_subset(fields, names)
