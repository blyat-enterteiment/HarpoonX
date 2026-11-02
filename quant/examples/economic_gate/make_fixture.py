"""Deterministic engineering fixture, not a trade experiment or market evidence."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from harpoon_quant.core import digest
from harpoon_quant.economic_gate import (
    INPUT_SCHEMA,
    PROTOCOL_SCHEMA,
    artifact_reference,
    register_protocol,
    seal_protocol,
)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def make_fixture(directory: str | Path, sessions: int = 64) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    first = datetime(2030, 1, 1, tzinfo=UTC)
    last = first + timedelta(days=sessions)
    protocol = seal_protocol({
        "schema": PROTOCOL_SCHEMA,
        "protocol_id": "SYNTHETIC_GATE_ENGINEERING_V1",
        "created_at": "2029-12-14T00:00:00+00:00",
        "research_only": True,
        "data_scope": "SYNTHETIC_ENGINEERING_ONLY",
        "currency": "USD",
        "equity_unit": "USD",
        "initial_equity_usd": 20000.0,
        "universe": ["FIXTURE_ETF", "FIXTURE_EQUITY"],
        "policy_hash": digest({"fixture_policy": "NO_EXTERNAL_ORDERS"}),
        "risk_hash": digest({"fixture_exposure_limit": 0.5}),
        "cost_hash": digest({"fixture_fees": 0.15, "fixture_operating_per_session": 0.05}),
        "code_hash": digest({"fixture_code": "NOT_A_TRADING_STRATEGY"}),
        "horizon_hours": 24.0,
        "max_drawdown_fraction": 0.10,
        "max_gross_exposure_fraction": 0.5,
        "risk_comparison": {"maximum_candidate_mean_exposure_ratio": 1.05, "maximum_candidate_mean_exposure_increment": 0.02, "justification": "Synthetic controls use exactly the same fixed exposure; no empirical risk equivalence is claimed."},
        "minimum_delta_ridge_log_growth": 0.00010,
        "minimum_delta_c0_log_growth": 0.0,
        "period": {
            "train_end": "2029-01-01T00:00:00+00:00",
            "validation_start": "2029-02-01T00:00:00+00:00",
            "validation_end": "2029-10-01T00:00:00+00:00",
            "test_start": first.isoformat(),
            "test_end": last.isoformat(),
        },
        "evaluation_sessions": [{"session_id": f"SYNTHETIC_SESSION_{index:04d}", "start_at": (first + timedelta(days=index)).isoformat(), "end_at": (first + timedelta(days=index + 1)).isoformat()} for index in range(sessions)],
        "walk_forward": {"selection_uses_final_test": False, "purge_sessions": 4, "embargo_sessions": 4, "justification": "Synthetic arithmetic fixture only; no model is fitted."},
        "dependence": {"method": "CIRCULAR_MOVING_BLOCK", "unit": "PORTFOLIO_SESSION", "block_lengths": [4], "dependency_horizon_sessions": 1, "minimum_sessions": 32, "minimum_complete_blocks": 8, "justification": "Engineering test of joint portfolio resampling; this is not an estimated market dependence horizon."},
        "statistics": {"family_alpha": 0.05, "bootstrap_repetitions": 32768, "seed": 1729, "minimum_tail_draws": 20},
        "search": {"total_attempts": 23, "historical_attempts": 23, "counter_reset": False},
    })
    journal = root / "preregistration.jsonl"
    if journal.exists():
        raise ValueError("FIXTURE_DIRECTORY_ALREADY_REGISTERED")
    registration = register_protocol(protocol, journal, "2029-12-15T00:00:00+00:00")
    history = {
        "schema": "HARPOON_SEARCH_HISTORY_1",
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "historical_attempts": 23,
        "historical_manifest_sha256": digest({"fixture_reference_only": "Historical HarpoonX counter floor 23; no historical artefact authenticated by this fixture"}),
        "new_attempts": [],
        "known_through": "2029-12-15T00:00:00+00:00",
        "financial_search_attempts_added": 0,
    }
    write_json(root / "search_history.json", history)
    rng = np.random.default_rng(7)
    common_noise = rng.normal(0, 0.0004, sessions)
    independent_noise = rng.normal(0, 0.0002, sessions)
    policies: dict[str, Any] = {}
    for name in ("C0", "RIDGE", "SVR"):
        item: dict[str, Any] = {
            "currency": "USD", "equity_unit": "USD", "universe": protocol["universe"],
            **{key: protocol[key] for key in ("policy_hash", "risk_hash", "cost_hash", "code_hash")},
            "valuation": "EXECUTABLE_SIDE_NET_OF_LIABILITIES", "all_costs_in_equity": True,
            "initial_positions": [], "curve": [],
        }
        equity = 20000.0
        for index in range(sessions):
            start = first + timedelta(days=index)
            end = start + timedelta(days=1)
            fee = 0.0 if name == "C0" else 0.15
            operating = 0.05
            if name == "C0":
                next_equity = equity - operating
            else:
                log_return = (0.00025 if name == "RIDGE" else 0.0014) + common_noise[index]
                if name == "SVR":
                    log_return += independent_noise[index]
                next_equity = equity * math.exp(float(log_return))
            item["curve"].append({
                "session_id": f"SYNTHETIC_SESSION_{index:04d}",
                "start_at": start.isoformat(), "end_at": end.isoformat(),
                "data_available_at": end.isoformat(),
                "source_hash": digest({"synthetic_record_index": index}),
                "equity_start_usd": equity, "equity_pre_flow_usd": equity,
                "external_flow_usd": 0.0, "equity_end_usd": next_equity,
                "gross_marked_pnl_usd": next_equity - equity + fee + operating,
                "fees_in_equity_usd": fee, "operating_costs_in_equity_usd": operating,
                "gross_exposure_fraction": 0.0 if name == "C0" else 0.35,
                "return_net": next_equity / equity - 1,
            })
            equity = next_equity
        item["terminal"] = {"at": last.isoformat(), "cash_usd": equity, "payables_usd": 0.0, "positions": []}
        policies[name] = item
    source = root / "fixture_policy.txt"
    source.write_text("Synthetic gate fixture only. No real coordinator, predictor or fills.\n", encoding="utf-8")
    source_ref = artifact_reference(source, root)
    parity: dict[str, Any] = {
        "schema": "HARPOON_COORDINATOR_REPLAY_1",
        "input_hash": digest({"synthetic_example": True}),
        "data_origin": "SYNTHETIC",
        "execution_origin": "MODELED",
        "scope": ["SYNTHETIC_GATE_UNIT_FIXTURE"],
        "source_hashes": {"fixture_policy.txt": source_ref["sha256"]},
        "checks": [{"id": "fixture_arithmetic_only", "expected_hash": digest([1, 2, 3]), "observed_hash": digest([1, 2, 3]), "passed": True, "mismatches": []}],
        "economic_bindings": {"policy_hash": protocol["policy_hash"], "risk_hash": protocol["risk_hash"]},
        "policy_parity_verified": False,
        "predictor_parity_verified": False,
        "financial_acceptance_allowed": False,
    }
    parity["artifact_hash"] = digest(parity)
    write_json(root / "parity_receipt.json", parity)
    evidence = {
        "schema": INPUT_SCHEMA,
        "protocol_hash": protocol["protocol_hash"],
        "generated_at": "2031-01-01T00:00:00+00:00",
        "execution_allowed": False, "liveApproved": False,
        "coordinator_input_hash": parity["input_hash"],
        "preregistration": {"journal": artifact_reference(journal, root), "record_hash": registration["record_hash"]},
        "search_history": artifact_reference(root / "search_history.json", root),
        "parity_receipt": artifact_reference(root / "parity_receipt.json", root),
        "parity_source_files": {"fixture_policy.txt": source_ref},
        "provenance": {
            "data_origin": "SYNTHETIC_ENGINEERING_ONLY", "price_origin": "SYNTHETIC",
            "execution_origin": "SYNTHETIC", "availability": "SYNTHETIC_CLOCK",
            "first_final_data_access_at": "2029-12-16T00:00:00+00:00",
            "prior_final_test_uses": [],
        },
        "policies": policies,
        "observational_artifacts": {},
        "purpose": "Synthetic regression of validation functions; does not add any financial research attempt.",
    }
    write_json(root / "protocol.json", protocol)
    write_json(root / "input.json", evidence)
    return protocol, evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sessions", type=int, default=64)
    args = parser.parse_args()
    make_fixture(args.output, args.sessions)
