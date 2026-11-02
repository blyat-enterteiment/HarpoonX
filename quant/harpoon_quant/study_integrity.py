"""Read-only verification of sealed economic studies before terminal analysis.

This validates local integrity and accounting consistency, not provenance from a
market-data provider. Legacy ENTRY/NAV ledgers require their separate trade list
to reconstruct exit cash; they do not independently prove executable fills.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from .core import digest
from .performance import report
from .recursive import Journal

ORIGIN = "SYNTHETIC_ENGINEERING_ONLY"
RUN_NAMES = (
    "baseline",
    "candidate",
    "cost_1_5",
    "cost_2",
    "gaps",
    "iv_crush",
    "liquidity",
    "delay",
    "outage",
)


class StudyIntegrityError(ValueError):
    """A sealed input or an accounting invariant failed verification."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise StudyIntegrityError(reason)


def _reject_constant(value: str) -> None:
    raise StudyIntegrityError("NONFINITE_JSON:" + value)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def _json(raw: bytes) -> dict[str, Any]:
    value = json.loads(
        raw, parse_constant=_reject_constant, object_pairs_hook=_unique_pairs
    )
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def _number(value: Any, name: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), name)
    number = float(value)
    require(math.isfinite(number), name)
    return number


def _time(value: Any) -> datetime:
    require(isinstance(value, str), "TIMESTAMP_REQUIRED")
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, "AWARE_TIMESTAMP_REQUIRED")
    return result.astimezone(UTC)


def _same(actual: Any, expected: Any, name: str) -> None:
    if isinstance(expected, dict):
        require(isinstance(actual, dict), name)
        require(set(actual) == set(expected), name + ":FIELDS")
        for key in expected:
            _same(actual[key], expected[key], name + ":" + key)
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), name)
        for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
            _same(left, right, name + ":" + str(index))
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        require(
            math.isclose(
                _number(actual, name), float(expected), rel_tol=1e-12, abs_tol=1e-10
            ),
            name,
        )
    else:
        require(type(actual) is type(expected) and actual == expected, name)


class _ReadOnlyJournal(Journal):
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            self.db.execute("BEGIN")
            self.verify()
        except BaseException:
            self.db.close()
            raise


@dataclass(frozen=True)
class VerifiedStudy:
    root: Path
    protocol: dict[str, Any]
    analysis: dict[str, Any]
    holdout: dict[str, Any]
    calendar: dict[str, Any]
    source_hashes: dict[str, str]
    budget: dict[str, Any]


def _registered(journal: Journal, key: str) -> dict[str, Any]:
    value = journal.get(key)
    require(isinstance(value, dict), "MISSING_REGISTRATION:" + key)
    return value


def _bindings(root: Path, *, allow_pending: bool = False) -> VerifiedStudy:
    names = (
        "study/protocol.json",
        "analysis_protocol.json",
        "study/holdout.json",
        "study/finalist.json",
        "evidence/alpaca_calendar.json",
    )
    raw = {name: (root / name).read_bytes() for name in names}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
    inputs = {name: _json(value) for name, value in raw.items()}
    protocol, analysis, holdout, finalist, calendar = (inputs[name] for name in names)
    journal = _ReadOnlyJournal(root / "study/optimizer.sqlite3")
    try:
        decision = journal.get("economic:decision")
        if decision is not None:
            require(isinstance(decision, dict), "DECISION_REGISTRATION_SCHEMA")
            if decision.get("publication_state") == "PENDING":
                require(allow_pending, "DECISION_PUBLICATION_PENDING")
            else:
                decision_hash = hashlib.sha256(
                    (root / "study/decision.json").read_bytes()
                ).hexdigest()
                require(
                    decision_hash == decision.get("result_hash"),
                    "PUBLISHED_DECISION_HASH_MISMATCH",
                )
        bindings = (
            ("economic:protocol", "hash", "study/protocol.json"),
            ("economic:analysis_protocol", "hash", "analysis_protocol.json"),
            ("economic:holdout", "result_hash", "study/holdout.json"),
        )
        for key, field, name in bindings:
            require(
                _registered(journal, key).get(field) == hashes[name],
                "SEALED_HASH_MISMATCH:" + name,
            )
        protocol_state = _registered(journal, "economic:protocol")
        if "protocol" in protocol_state:
            require(
                digest(protocol_state["protocol"]) == digest(protocol),
                "REGISTERED_PROTOCOL_CONTENT",
            )
        sealed_finalist = _registered(journal, "economic:finalist")
        require(digest(finalist) == digest(sealed_finalist), "FINALIST_FILE_MISMATCH")
        require(
            digest(holdout["finalist"]) == digest(sealed_finalist),
            "HOLDOUT_FINALIST_MISMATCH",
        )
        require(
            finalist["protocol_hash"] == hashes["study/protocol.json"],
            "FINALIST_PROTOCOL_BINDING",
        )
        implementation = _registered(journal, "economic:implementation")
        require(
            finalist["code_hash"] == implementation.get("hash"), "FINALIST_CODE_BINDING"
        )
        frozen = root / "work/HarpoonX_Motor_Quant/harpoon_quant"
        code_hash = hashlib.sha256(
            b"".join(
                (frozen / name).read_bytes()
                for name in ("economic_lab.py", "performance.py", "recursive.py")
            )
        ).hexdigest()
        require(code_hash == finalist["code_hash"], "FROZEN_IMPLEMENTATION_MISMATCH")
        hashes["frozen_implementation"] = code_hash
        require(
            protocol["calendar_file_sha256"] == hashes["evidence/alpaca_calendar.json"],
            "CALENDAR_BINDING",
        )
        holdout_state = _registered(journal, "economic:holdout")
        require(
            holdout_state.get("stage") == "COMPLETE"
            and holdout_state.get("execution_allowed") is False,
            "HOLDOUT_NOT_COMPLETE_OFFLINE",
        )
        domain = digest({"account": "SYNTH_48_OPTIONS", "origin": ORIGIN})
        count = journal.db.execute(
            "SELECT COUNT(*) FROM optimizer_holdouts WHERE lo=? AND hi=? AND domain=? AND campaign=?",
            (
                protocol["holdout_start"],
                protocol["holdout_end"],
                domain,
                protocol["study_id"],
            ),
        ).fetchone()[0]
        require(count == 1, "HOLDOUT_RESERVATION_MISSING")
        budget = _registered(journal, "budget")
        require(
            isinstance(budget.get("spent"), int)
            and isinstance(budget.get("limit"), int),
            "BUDGET_SCHEMA",
        )
        require(
            0 < budget["spent"] <= budget["limit"] <= analysis["family_bound"],
            "BUDGET_FAMILY_BINDING",
        )
    finally:
        journal.close()
    return VerifiedStudy(root, protocol, analysis, holdout, calendar, hashes, budget)


def _marks(calendar: dict[str, Any], start: str, end: str) -> list[datetime]:
    zone = ZoneInfo("America/New_York")
    marks = []
    for row in calendar["calendar"]:
        if start <= row["date"] <= end:
            opening = datetime.fromisoformat(row["open"]).replace(tzinfo=zone)
            closing = datetime.fromisoformat(row["close"]).replace(tzinfo=zone)
            marks.extend(
                [
                    opening + timedelta(minutes=15),
                    opening + timedelta(minutes=30),
                    closing - timedelta(minutes=15),
                ]
            )
    return sorted({mark.astimezone(UTC) for mark in marks})


def _reconcile_run(
    run: dict[str, Any], study: VerifiedStudy, marks: list[datetime]
) -> None:
    protocol = study.protocol
    require(
        run["origin"] == ORIGIN and run["execution_allowed"] is False,
        "RUN_NOT_OFFLINE_SYNTHETIC",
    )
    capital = _number(protocol["capital"], "CAPITAL")
    start = datetime.fromisoformat(protocol["holdout_start"]).date()
    stop = datetime.fromisoformat(protocol["holdout_end"]).date()
    dates = [
        (start + timedelta(days=index)).isoformat()
        for index in range((stop - start).days + 1)
    ]
    require(run["dates"] == dates, "RUN_DATE_ALIGNMENT")
    returns = [_number(value, "RETURN_DOMAIN") for value in run["returns"]]
    require(
        len(returns) == len(dates) and all(value > -1 for value in returns),
        "RUN_RETURN_DOMAIN",
    )
    growth = float(np.log1p(returns).mean())
    _same(run["mean_log_growth"], growth, "LOG_GROWTH_RECONCILIATION")
    entries: dict[tuple[int, datetime], dict[str, Any]] = {}
    cash_changes: dict[datetime, float] = {}
    navs: list[dict[str, Any]] = []
    previous: datetime | None = None
    for event in run["ledger"]:
        at = _time(event["at"])
        require(previous is None or at >= previous, "LEDGER_TIME_ORDER")
        require(at in marks, "LEDGER_TIMESTAMP_NOT_IN_CALENDAR")
        previous = at
        if event["kind"] == "ENTRY":
            key = (event["asset"], at)
            require(key not in entries, "DUPLICATE_POSITION_ENTRY")
            lots = event["lots"]
            require(
                isinstance(lots, int) and not isinstance(lots, bool) and lots > 0,
                "ENTRY_LOTS",
            )
            cash_change = _number(event["cash_change"], "ENTRY_CASH")
            require(cash_change < 0, "ENTRY_CASH_DIRECTION")
            _number(event["risk"], "ENTRY_RISK")
            entries[key] = dict(lots=lots, funding=-cash_change / lots, closures=[])
            cash_changes[at] = cash_changes.get(at, 0.0) + cash_change
        elif event["kind"] == "NAV":
            require(
                isinstance(event["open_positions"], int)
                and event["open_positions"] >= 0,
                "OPEN_POSITION_COUNT",
            )
            _number(event["cash"], "NAV_CASH")
            _number(event["nav"], "NAV_VALUE")
            navs.append(event)
        else:
            raise StudyIntegrityError(
                "UNSUPPORTED_LEGACY_LEDGER_EVENT:" + str(event["kind"])
            )
    require([_time(event["at"]) for event in navs] == marks, "NAV_MARKS_INCOMPLETE")
    for trade in run["trades"]:
        entry, exit_at = _time(trade["entry_at"]), _time(trade["exit_at"])
        require(
            entry < exit_at <= entry + timedelta(hours=72) and exit_at in marks,
            "HOLDING_OR_EXIT_TIME",
        )
        key = (trade["asset"], entry)
        require(key in entries, "TRADE_WITHOUT_ENTRY")
        quantity = trade["lots"]
        require(
            isinstance(quantity, int)
            and not isinstance(quantity, bool)
            and quantity > 0,
            "EXIT_LOTS",
        )
        require(trade["kind"] in {"stock", "option"}, "TRADE_KIND")
        pnl = _number(trade["net_pnl_usd"], "TRADE_PNL")
        require(_number(trade["cost_usd"], "TRADE_COST") >= 0, "NEGATIVE_TRADE_COST")
        position = entries[key]
        position["closures"].append((exit_at, quantity))
        cash_changes[exit_at] = (
            cash_changes.get(exit_at, 0.0) + position["funding"] * quantity + pnl
        )
    for position in entries.values():
        require(
            sum(quantity for _, quantity in position["closures"]) == position["lots"],
            "POSITION_LOTS_NOT_CLOSED",
        )
    cash = capital
    daily: dict[str, float] = {}
    for event in navs:
        at = _time(event["at"])
        cash += cash_changes.get(at, 0.0)
        require(
            math.isclose(cash, event["cash"], rel_tol=1e-12, abs_tol=1e-7),
            "CASH_FLOW_RECONCILIATION",
        )
        open_positions = sum(
            entry <= at
            and position["lots"]
            > sum(quantity for closed, quantity in position["closures"] if closed <= at)
            for (_, entry), position in entries.items()
        )
        require(open_positions == event["open_positions"], "INVENTORY_RECONCILIATION")
        if not open_positions:
            require(
                math.isclose(cash, event["nav"], rel_tol=1e-12, abs_tol=1e-7),
                "FLAT_NAV_CASH_RECONCILIATION",
            )
        daily[at.date().isoformat()] = event["nav"]
    value = capital
    reconstructed = []
    for date in dates:
        value = daily.get(date, value)
        reconstructed.append(value)
    compounded = capital * np.cumprod(1 + np.asarray(returns))
    require(
        bool(np.allclose(compounded, reconstructed, rtol=1e-12, atol=1e-7)),
        "RETURNS_NAV_RECONCILIATION",
    )
    require(
        math.isclose(
            value - capital,
            sum(t["net_pnl_usd"] for t in run["trades"]),
            rel_tol=1e-12,
            abs_tol=1e-7,
        ),
        "TOTAL_PNL_RECONCILIATION",
    )
    expected = report(
        dict(
            origin=ORIGIN,
            return_basis="NET_FLOW_ADJUSTED",
            returns=returns,
            times=[date + "T23:59:59+00:00" for date in dates],
            initial_equity=capital,
            periods_per_year=365,
            sampling="DAILY_UTC_CALENDAR",
            trades=run["trades"],
        ),
        schema_version=1,
    )
    _same(run["metrics"], expected, "METRICS_RECONCILIATION")


def load_verified_study(root: Path, *, allow_pending: bool = False) -> VerifiedStudy:
    """Validate sealed bytes, frozen bindings, all paths and available accounting."""
    try:
        study = _bindings(root, allow_pending=allow_pending)
        protocol = study.protocol
        require(
            protocol["schema"] == "ECONOMIC_STUDY_1" and protocol["origin"] == ORIGIN,
            "STUDY_SCHEMA_OR_ORIGIN",
        )
        require(
            [row["seed"] for row in study.holdout["results"]]
            == protocol["holdout_seeds"],
            "HOLDOUT_SEEDS_OR_COUNT",
        )
        require(
            len(set(protocol["holdout_seeds"])) == len(protocol["holdout_seeds"]),
            "DUPLICATE_HOLDOUT_SEED",
        )
        marks = _marks(
            study.calendar, protocol["holdout_start"], protocol["holdout_end"]
        )
        require(bool(marks), "HOLDOUT_CALENDAR_EMPTY")
        for row in study.holdout["results"]:
            require(set(row["runs"]) == set(RUN_NAMES), "HOLDOUT_RUNS_INCOMPLETE")
            for name, run in row["runs"].items():
                flags = (
                    ""
                    if name == "baseline"
                    else "".join(study.holdout["finalist"]["flags"])
                )
                require(run["policy"] == {"flags": flags}, "RUN_POLICY_BINDING")
                _reconcile_run(run, study, marks)
        return study
    except StudyIntegrityError:
        raise
    except (
        KeyError,
        TypeError,
        ValueError,
        IndexError,
        OSError,
        sqlite3.Error,
    ) as error:
        raise StudyIntegrityError("STUDY_INPUT_INVALID:" + str(error)) from error


def assert_inputs_unchanged(
    study: VerifiedStudy, *, allow_pending: bool = False
) -> None:
    """Recheck bindings immediately before committing an expensive analysis."""
    current = _bindings(study.root, allow_pending=allow_pending)
    require(
        current.source_hashes == study.source_hashes, "STUDY_CHANGED_DURING_ANALYSIS"
    )
    require(current.budget == study.budget, "BUDGET_CHANGED_DURING_ANALYSIS")
