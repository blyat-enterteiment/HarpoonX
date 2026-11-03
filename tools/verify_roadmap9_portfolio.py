"""Separate Decimal audit of the published, flat USD-equity engineering fixture.

Imports neither the portfolio optimizer, its fee ledger nor its risk supervisor.
Exhaustive native-share partial fills independently test the corner certificate
on this small fixture. This is internal engineering verification, not an external
review or evidence of a profitable or executable trading policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, getcontext
from itertools import product
from pathlib import Path
from typing import Any

getcontext().prec = 50
D = Decimal
ZERO = D(0)


def dec(value: Any) -> Decimal:
    result = D(str(value))
    if not result.is_finite():
        raise ValueError("NONFINITE_FIXTURE")
    return result


def check(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text())
    supplied, proposal = body["example"]["input"], body["example"]["result"]
    state, forecast, cfg = (supplied[k] for k in ("state", "forecast", "config"))
    assets, profiles = state["assets"], supplied["fee_profiles"]
    if any(a["current_lots"] != 0 or a["book"] not in {"equity", "etf"} for a in assets):
        raise ValueError("AUDITOR_SCOPE_FLAT_USD_EQUITY_FIXTURE")
    capital = dec(state["cash_usd"]) + dec(state["receivables_usd"])
    overhead = dec(cfg["risk"]["overhead_usd_per_day"]) * dec(forecast["horizon_hours"]) / 24
    averages = [dec(m) * D(2) ** (-dec(age) / dec(half)) for m, age, half in zip(
        forecast["mean"], forecast["signal_age_hours"], forecast["alpha_half_life_hours"], strict=True)]

    def account(qtys: tuple[int, ...]) -> dict[str, Any]:
        cash = dec(state["cash_usd"])
        entry_cost, exit_cost = ZERO, ZERO
        marks: list[Decimal] = []
        net_values: list[Decimal] = []
        factors: dict[str, Decimal] = {}
        for asset, quantity in zip(assets, qtys, strict=True):
            bid, ask = dec(asset["bid"]), dec(asset["ask"])
            mid = (bid + ask) / 2
            profile = profiles[asset["symbol"]]
            if profile["charge_mode"] != "QUOTE_PER_UNIT" or profile["quote_asset"] != "USD":
                raise ValueError("AUDITOR_SCOPE_USD_PER_SHARE")
            slip = dec(asset["slippage_bps"]) / 10000
            fee = quantity * dec(profile["quote_fee_per_unit"]) + (
                dec(profile["quote_fixed_per_order"]) if quantity else ZERO)
            debit = quantity * ask * (1 + slip) + fee
            final_sale_before_fee = quantity * bid * (1 - slip)
            cash -= debit
            entry_cost += debit - quantity * mid
            exit_cost += quantity * mid - final_sale_before_fee + fee
            marks.append(quantity * mid)
            net_values.append(final_sale_before_fee)
            factors[asset["factor"]] = factors.get(asset["factor"], ZERO) + quantity * mid
        equity = cash + dec(state["receivables_usd"]) + sum(marks, ZERO)
        loads = [value / capital for value in net_values]
        mean = sum((x * y for x, y in zip(loads, averages, strict=True)), ZERO)
        variance = sum((loads[i] * loads[j] * dec(forecast["return_covariance"][i][j])
                       for i in range(len(loads)) for j in range(len(loads))), ZERO)
        error_variance = sum((loads[i] * loads[j] * dec(forecast["mean_error_covariance"][i][j])
                             for i in range(len(loads)) for j in range(len(loads))), ZERO)
        cost = entry_cost + exit_cost + overhead
        score = mean - dec(cfg["variance_aversion"]) * variance / 2 - cost / capital \
            - dec(cfg["risk"]["uncertainty_z"]) * error_variance.sqrt()
        losses = [(cost - sum((value * dec(r) for value, r in zip(net_values, row, strict=True)), ZERO),
                   dec(weight)) for row, weight in zip(forecast["scenario_returns"], forecast["scenario_weights"], strict=True)]
        mass, weighted = D('.05'), ZERO
        for loss, probability in sorted(losses, reverse=True):
            used = min(mass, probability)
            weighted += loss * used
            mass -= used
            if mass == 0:
                break
        tail = max(ZERO, weighted / D('.05'))
        stress = max([ZERO, *[cost - sum((value * dec(r) for value, r in zip(net_values, row, strict=True)), ZERO)
                                for row in forecast["stress_returns"]]])
        safe = (cash >= dec(state["pending_cash_usd"]) and
                dec(state["cash_usd"]) - cash + overhead <= dec(state["cash_usd"]) - dec(state["pending_cash_usd"]) and
                sum(marks, ZERO) <= equity * dec(cfg["risk"]["gross_fraction"]) and
                all(m <= equity * dec(cfg["risk"]["asset_fraction"]) for m in marks) and
                all(m <= equity * dec(cfg["risk"]["factor_fraction"]) for m in factors.values()) and
                tail <= capital * dec(cfg["risk"]["tail_fraction"]) and
                stress <= capital * dec(cfg["risk"]["stress_fraction"]))
        return {"cash": cash, "equity": equity, "immediate_cost": entry_cost,
                "exit_cost": exit_cost, "score": score, "tail": tail, "stress": stress, "safe": safe}

    quantities = tuple(int(q) for q in proposal["chosen"]["full_fill"]["native_quantities"])
    if len(quantities) > 4 or any(q < 0 or q > 100 for q in quantities):
        raise ValueError("EXHAUSTIVE_FIXTURE_BUDGET")
    combinations = 1
    for q in quantities:
        combinations *= q + 1
    if combinations > 10000:
        raise ValueError("EXHAUSTIVE_FIXTURE_BUDGET")
    selected = account(quantities)
    expected = proposal["chosen"]["full_fill"]
    matches = {}
    mapping = {"cash": "cash_after_this_fill_subset_usd", "equity": "equity_after_this_fill_subset_usd",
               "immediate_cost": "immediate_transaction_cost_usd", "exit_cost": "future_liquidation_cost_at_zero_return_usd",
               "score": "score", "tail": "cvar_loss_usd", "stress": "stress_loss_usd"}
    for local, supplied_key in mapping.items():
        difference = abs(selected[local] - dec(expected[supplied_key]))
        matches[local] = {"independent_decimal": str(selected[local]), "absolute_difference": str(difference)}
        if difference > D('1e-10'):
            raise ValueError("INDEPENDENT_REPRICE_MISMATCH:" + local)
    partial = [account(q) for q in product(*(range(n + 1) for n in quantities))]
    if not all(row["safe"] for row in partial):
        raise ValueError("UNSAFE_EXHAUSTIVE_PARTIAL_FILL")
    return {"schema": "HARPOON_ROADMAP9_SEPARATE_PORTFOLIO_CHECK_1", "verified": True,
            "origin": "SYNTHETIC_ENGINEERING_ONLY", "input_example_sha256": hashlib.sha256(json.dumps(
                body['example'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
            "audited_component_source_hashes": body["source_hashes"],
            "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "decimal_precision": 50, "absolute_tolerance": "1e-10", "comparisons": matches,
            "exhaustive_native_share_fill_combinations": len(partial),
            "all_exhaustive_partials_within_declared_limits": True,
            "maximum_partial_cvar_usd": str(max(row["tail"] for row in partial)),
            "scope": "INDEPENDENT_REPRICE_OF_ONE_PUBLISHED_FLAT_USD_FIXTURE_NOT_ALL_POLICIES_OR_MARKET_STATES",
            "imports_optimizer_or_fee_ledger": False, "external_review_completed": False,
            "economic_evaluation_completed": False, "execution_allowed": False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check(args.component)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'verified': True, 'partial_fill_combinations': result['exhaustive_native_share_fill_combinations']}))
