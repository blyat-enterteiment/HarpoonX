"""Append-only registration for the bounded roadmap research family.

The hash chain detects local inconsistency. It is not external attestation and
cannot detect replacement of an entire file without an independently held head.
Prior budgets are imported with their provenance and incompleteness preserved.
Recipe slots and policy/scenario measurements are deliberately separate counts.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "HARPOON_ROADMAP9_REGISTRY_1"
MAX_RECIPES = 6
MAX_HYPOTHESES = 3
MAX_BYTES = 8 * 1024 * 1024
RECIPE_FIELDS = (
    "features_and_targets",
    "training_and_refit_rule",
    "universe",
    "allocation",
    "entry",
    "exit",
    "risk_limits",
    "cost_profile",
    "data_availability",
    "selection_rule",
    "evaluation_and_stopping",
)


def digest(value: Any) -> str:
    """Hash an unambiguous, finite JSON value."""
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _is_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _objects(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _load(path: Path) -> list[dict[str, Any]]:
    _require(path.is_file(), "EXISTING_REGISTRY_REQUIRED")
    raw = path.read_bytes()
    _require(0 < len(raw) <= MAX_BYTES and raw.endswith(b"\n"), "REGISTRY_BYTES")
    events = [json.loads(line, object_pairs_hook=_objects) for line in raw.splitlines()]
    _require(all(isinstance(e, dict) for e in events), "REGISTRY_RECORD_TYPE")
    return events


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _validate_bindings(bindings: dict[str, str]) -> None:
    _require(isinstance(bindings, dict) and bool(bindings), "BINDINGS_REQUIRED")
    _require(
        all(isinstance(k, str) and k and _is_hash(v) for k, v in bindings.items()),
        "BINDING_HASH_REQUIRED",
    )
    for prefix in ("code", "data", "settings", "plan"):
        _require(
            any(k == prefix or k.startswith(prefix + ":") for k in bindings),
            "MISSING_BINDING:" + prefix,
        )


def _validate_recipes(recipes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    _require(
        isinstance(recipes, list) and 1 <= len(recipes) <= MAX_RECIPES,
        "RECIPE_BUDGET_EXCEEDED",
    )
    ids: set[str] = set()
    hypotheses: set[str] = set()
    keys: list[tuple[str, str]] = []
    for recipe in recipes:
        _require(isinstance(recipe, dict), "RECIPE_OBJECT_REQUIRED")
        rid = recipe.get("id")
        hyp = recipe.get("hypothesis")
        if not isinstance(rid, str) or not rid or rid in ids:
            raise ValueError("DUPLICATE_OR_MISSING_RECIPE_ID")
        if not isinstance(hyp, str) or hyp not in {"H1", "H2", "H3"}:
            raise ValueError("HYPOTHESIS_NOT_REGISTERED")
        ids.add(rid)
        hypotheses.add(hyp)
        for field in RECIPE_FIELDS:
            _require(
                field in recipe and recipe[field] not in (None, "", [], {}),
                "INCOMPLETE_RECIPE:" + field,
            )
        scenarios = recipe.get("scenarios")
        if (
            not isinstance(scenarios, list)
            or len(scenarios) != 2
            or set(scenarios) != {"NOMINAL", "STRESS"}
        ):
            raise ValueError("COST_SCENARIOS_REQUIRED")
        keys.extend((rid, scenario) for scenario in scenarios)
        digest(recipe)  # Reject NaN, infinity and non-JSON configuration values.
    _require(len(hypotheses) <= MAX_HYPOTHESES, "HYPOTHESIS_BUDGET_EXCEEDED")
    return keys


def _validate_history(history: dict[str, Any]) -> None:
    _require(isinstance(history, dict), "PRIOR_HISTORY_REQUIRED")
    spent, limit = history.get("reported_spent"), history.get("limit")
    _require(
        type(spent) is int and type(limit) is int and 0 < spent <= limit,
        "PRIOR_BUDGET_REQUIRED_NO_RESET",
    )
    _require(
        history.get("global_history_complete") is False,
        "GLOBAL_COMPLETENESS_NOT_ESTABLISHED",
    )
    sources = history.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("PRIOR_SOURCES_REQUIRED")
    paths: set[str] = set()
    for source in sources:
        _require(
            isinstance(source, dict)
            and isinstance(source.get("path"), str)
            and bool(source["path"])
            and _is_hash(source.get("sha256")),
            "PRIOR_SOURCE_BINDING_REQUIRED",
        )
        _require(source["path"] not in paths, "DUPLICATE_HISTORY_SOURCE")
        paths.add(source["path"])


def documented_history(project_root: Path | str) -> dict[str, Any]:
    """Import the recovered 47 -> 53 lineage without certifying all past trials."""
    root = Path(project_root)
    admission_path = "evidence/residual_30_18_0/registration/admission.json"
    freeze_path = "research/research9_30_19/freeze.json"
    amendment_path = "research/research9_30_19/amendment_01.json"
    documents: dict[str, Any] = {}
    sources = []
    for name in (admission_path, freeze_path, amendment_path):
        raw = (root / name).read_bytes()
        documents[name] = json.loads(raw, object_pairs_hook=_objects)
        sources.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest()})
    admitted, frozen = documents[admission_path], documents[freeze_path]
    parent = admitted["budget"]["spent"]
    count = frozen["new_policy_scenario_measurements"]
    _require(
        type(parent) is int and type(count) is int and count > 0,
        "DOCUMENTED_HISTORY_COUNTS",
    )
    _require(
        frozen["declared_budget_parent"] == parent
        and frozen["declared_budget_after"] == parent + count
        and frozen["declared_budget_limit"] == admitted["budget"]["limit"],
        "DOCUMENTED_HISTORY_DISCONTINUITY",
    )
    _require(
        frozen["global_budget_independently_reconciled"] is False
        and frozen["history_already_seen"] is True,
        "PRIOR_HISTORY_SCOPE_CHANGED",
    )
    return {
        "reported_spent": frozen["declared_budget_after"],
        "limit": frozen["declared_budget_limit"],
        "sources": sources,
        "global_history_complete": False,
        "scope": "RECOVERED_DOCUMENTED_LINEAGE_NOT_GLOBAL_ATTEMPT_CENSUS",
        "inherited_admitted_count": parent,
        "later_declared_measurements": count,
        "known_engineering_retry_retained": amendment_path,
        "independent_preregistration": False,
        "history_already_seen": True,
    }


def _verify(
    events: list[dict[str, Any]], recipes: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    previous = "GENESIS"
    last_time: datetime | None = None
    for i, event in enumerate(events):
        _require(
            set(event) == {"sequence", "previous", "payload", "hash"}, "EVENT_FIELDS"
        )
        _require(
            event["sequence"] == i and event["previous"] == previous, "CHAIN_SEQUENCE"
        )
        _require(
            event["hash"]
            == digest({k: event[k] for k in ("sequence", "previous", "payload")}),
            "CHAIN_HASH",
        )
        stamp = datetime.fromisoformat(event["payload"]["at"])
        _require(stamp.tzinfo is not None, "AWARE_TIMESTAMP_REQUIRED")
        _require(last_time is None or stamp >= last_time, "NON_MONOTONIC_RECORD_TIME")
        last_time, previous = stamp, event["hash"]
    frozen = events[0]["payload"]
    _require(
        frozen.get("type") == "FREEZE" and frozen.get("schema") == SCHEMA,
        "FREEZE_REQUIRED",
    )
    keys = _validate_recipes(frozen["recipes"])
    _validate_history(frozen["history"])
    _validate_bindings(frozen["bindings"])
    _require(
        frozen["history"]["reported_spent"] + len(keys) <= frozen["history"]["limit"],
        "LIFETIME_BUDGET_EXCEEDED",
    )
    if recipes is not None:
        _require(digest(recipes) == digest(frozen["recipes"]), "FROZEN_RECIPE_CHANGED")
    registered = set(keys)
    started: dict[tuple[str, str], dict[str, Any]] = {}
    completed: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events[1:]:
        payload = event["payload"]
        key = (payload.get("recipe_id"), payload.get("scenario"))
        _require(key in registered, "UNREGISTERED_MEASUREMENT")
        _require(
            payload.get("bindings_hash") == digest(frozen["bindings"]),
            "MEASUREMENT_BINDING_CHANGED",
        )
        if payload["type"] == "START":
            _require(key not in started, "DUPLICATE_START")
            started[key] = payload
        elif payload["type"] == "RESULT":
            _require(
                key in started and key not in completed, "RESULT_WITHOUT_UNIQUE_START"
            )
            _require(
                _is_hash(payload.get("result_sha256"))
                and isinstance(payload.get("result_path"), str),
                "RESULT_BINDING_REQUIRED",
            )
            _require(
                payload.get("new_independent_observations") is False,
                "REPEAT_IS_NOT_NEW_DATA",
            )
            completed[key] = payload
        else:
            raise ValueError("UNKNOWN_EVENT")
    return {
        "verified": True,
        "schema": SCHEMA,
        "head": previous,
        "freeze_hash": events[0]["hash"],
        "recipe_count": len(frozen["recipes"]),
        "hypothesis_count": len({r["hypothesis"] for r in frozen["recipes"]}),
        "reserved_policy_scenario_measurements": len(keys),
        "started_measurements": len(started),
        "completed_measurements": len(completed),
        "prior_reported_measurements": frozen["history"]["reported_spent"],
        "reported_plus_reserved_measurements": frozen["history"]["reported_spent"]
        + len(keys),
        "reported_lifetime_limit": frozen["history"]["limit"],
        "global_history_complete": False,
        "global_selection_correction_verified": False,
        "independent_preregistration": False,
        "execution_allowed": False,
        "financial_acceptance_allowed": False,
        "level9_accredited": False,
        "scope": "LOCAL_HASH_CHAIN_AND_RESERVED_BUDGET_WITH_INCOMPLETE_IMPORTED_HISTORY",
    }


def _append(path: Path, events: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    body = {
        "sequence": len(events),
        "previous": events[-1]["hash"] if events else "GENESIS",
        "payload": payload,
    }
    event = {**body, "hash": digest(body)}
    proposed = [*events, event]
    _verify(proposed)
    mode = "ab" if path.exists() else "xb"
    raw = (
        json.dumps(event, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode()
    _require(
        (path.stat().st_size if path.exists() else 0) + len(raw) <= MAX_BYTES,
        "REGISTRY_BYTES",
    )
    with path.open(mode) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def freeze_registry(
    path: Path | str,
    recipes: list[dict[str, Any]],
    history: dict[str, Any],
    bindings: dict[str, str],
) -> dict[str, Any]:
    """Reserve every complete recipe/scenario before the first measurement."""
    path = Path(path)
    _validate_recipes(recipes)
    _validate_history(history)
    _validate_bindings(bindings)
    with _locked(path):
        if path.exists():
            events = _load(path)
            result = _verify(events, recipes)
            frozen = events[0]["payload"]
            _require(
                frozen["bindings"] == bindings and frozen["history"] == history,
                "FREEZE_BINDING_CONFLICT",
            )
            return result
        payload = {
            "type": "FREEZE",
            "at": _now(),
            "schema": SCHEMA,
            "recipes": recipes,
            "history": history,
            "bindings": bindings,
        }
        _append(path, [], payload)
        return _verify(_load(path), recipes)


def begin_measurement(
    path: Path | str, recipe_id: str, scenario: str, current_bindings: dict[str, str]
) -> dict[str, Any]:
    """Record start before accessing the economic outcome; retry is idempotent."""
    path = Path(path)
    with _locked(path):
        events = _load(path)
        _verify(events)
        frozen = events[0]["payload"]
        _require(current_bindings == frozen["bindings"], "MEASUREMENT_BINDING_CHANGED")
        for event in events[1:]:
            p = event["payload"]
            if p["type"] == "START" and (p["recipe_id"], p["scenario"]) == (
                recipe_id,
                scenario,
            ):
                return _verify(events)
        _append(
            path,
            events,
            {
                "type": "START",
                "at": _now(),
                "recipe_id": recipe_id,
                "scenario": scenario,
                "bindings_hash": digest(current_bindings),
            },
        )
        return _verify(_load(path))


def record_measurement(
    path: Path | str, recipe_id: str, scenario: str, result_path: Path | str
) -> dict[str, Any]:
    """Bind one result file; repeated identical receipts consume no new slot."""
    path, result_path = Path(path), Path(result_path)
    _require(result_path.is_file(), "RESULT_FILE_REQUIRED")
    result_hash = hashlib.sha256(result_path.read_bytes()).hexdigest()
    with _locked(path):
        events = _load(path)
        _verify(events)
        for event in events[1:]:
            p = event["payload"]
            if p["type"] == "RESULT" and (p["recipe_id"], p["scenario"]) == (
                recipe_id,
                scenario,
            ):
                _require(
                    p["result_sha256"] == result_hash, "MEASUREMENT_RESULT_CONFLICT"
                )
                return _verify(events)
        _append(
            path,
            events,
            {
                "type": "RESULT",
                "at": _now(),
                "recipe_id": recipe_id,
                "scenario": scenario,
                "result_path": str(result_path),
                "result_sha256": result_hash,
                "new_independent_observations": False,
                "bindings_hash": digest(events[0]["payload"]["bindings"]),
            },
        )
        return _verify(_load(path))


def verify_registry(
    path: Path | str,
    recipes: list[dict[str, Any]] | None = None,
    verify_results: bool = True,
) -> dict[str, Any]:
    """Check frozen specification, event semantics and optional result bytes."""
    path = Path(path)
    with _locked(path):
        events = _load(path)
        result = _verify(events, recipes)
        if verify_results:
            for event in events[1:]:
                payload = event["payload"]
                if payload["type"] == "RESULT":
                    file = Path(payload["result_path"])
                    _require(file.is_file(), "RESULT_FILE_MISSING")
                    _require(
                        hashlib.sha256(file.read_bytes()).hexdigest()
                        == payload["result_sha256"],
                        "RESULT_HASH_CHANGED",
                    )
        return result
