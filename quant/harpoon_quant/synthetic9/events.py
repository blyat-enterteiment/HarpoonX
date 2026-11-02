"""Bounded, hash-linked synthetic event transport. Hashes establish local integrity."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core import digest
from ..frontier.contracts import require
from . import ORIGIN


def number(value: Any, *, positive: bool = False) -> float:
    require(type(value) in (int, float), "NUMBER_TYPE")
    out = float(value)
    require(
        bool(np.isfinite(out)) and (out > 0 if positive else out >= 0), "NUMBER_DOMAIN"
    )
    return out


def clock(value: Any) -> int:
    require(type(value) is int and value >= 0, "CLOCK_DOMAIN")
    return value


def link(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    require(len(events) <= 200_000, "EVENT_BUDGET")
    chain = []
    previous = None
    for i, body in enumerate(events):
        item: dict[str, Any] = {"sequence": i, "previous_hash": previous, "event": body}
        item["hash"] = digest(item)
        previous = item["hash"]
        chain.append(item)
    return chain


def unlink(chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    require(0 < len(chain) <= 200_000, "EVENT_BUDGET")
    previous = None
    out = []
    for i, item in enumerate(chain):
        require(
            item["sequence"] == i and item["previous_hash"] == previous,
            "EVENT_CHAIN_ORDER",
        )
        require(
            digest({k: v for k, v in item.items() if k != "hash"}) == item["hash"],
            "EVENT_HASH",
        )
        require(item["event"]["origin"] == ORIGIN, "SYNTHETIC_EVENT_ORIGIN")
        out.append(item["event"])
        previous = item["hash"]
    return out
