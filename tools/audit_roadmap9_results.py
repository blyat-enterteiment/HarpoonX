#!/usr/bin/env python3
"""Independent Python reconciliation of roadmap account outputs.

Derived from the retained historical auditor (which remains unchanged). The
explicit adaptations are replay identity and UTC-calendar cost accrual; all
inventory, fees, dividend, reservation, cash and compounding checks remain.
It does not fit or select any strategy, and does not certify observed fills.
"""

from __future__ import annotations

import bisect
import math
from typing import Any

from audit_historical_results import (
    RETURN_ATOL,
    USD_ATOL,
    audit_snapshot,
    close_known,
    entitlement_total,
    near,
    need,
    reservation_snapshot,
)

BASE_AUDITOR_SHA256 = "6fb811c809fab3615ce0abe30b2588ba0d1b8cc1653d05557227a6f24d4d3b52"


def audit_report(
    report: dict[str, Any], protocol: dict[str, Any], dataset: dict[str, Any], key: str
) -> dict[str, Any]:
    scenario, policy = key.split(":")
    need(
        report["schema"] == "HARPOON_HISTORICAL_PORTFOLIO_1"
        and report["origin"] == "HISTORICAL"
        and report["execution"] == "MODELED_OHLCV"
        and report["scenario"] == scenario
        and report["policy"] == policy,
        key + ":REPORT_IDENTITY",
    )
    need(
        report["financial_acceptance_allowed"] is False
        and report["liveApproved"] is False
        and report["native_control_is_production_coordinator"] is False
        and report["native_control"] == "NATIVE_HISTORICAL_ULTIMATE_ROADMAP9",
        key + ":AUTHORITY",
    )
    need(report["portfolio"]["limits"] == protocol["limits"], key + ":LIMITS_BINDING")
    periods, universe, limits = (
        protocol["periods"],
        protocol["universe"],
        protocol["limits"],
    )
    cost = protocol["scenarios"][scenario]
    fee, daily_cost = (
        cost["commission_usd_per_share_per_side"],
        cost["external_cost_usd_per_calendar_day"],
    )
    sessions = [
        s
        for s in dataset["sessions"]
        if periods["evaluation_start"] <= s["date"] <= periods["evaluation_end"]
    ]
    curve, trades, states = report["curve"], report["funded"], report["states"]
    need(
        len(curve) > 0
        and [r["session_id"] for r in curve] == [s["date"] for s in sessions],
        key + ":COMPLETE_CALENDAR",
    )
    near(limits["capitalUsd"], 20000, key + ":REGISTERED_INITIAL_CAPITAL")
    near(curve[0]["equity_start_usd"], limits["capitalUsd"], key + ":INITIAL_CAPITAL")
    records = report["reservationBook"]["reservations"]
    need(
        report["reservationBook"]["schema"] == "HARPOON_FUNDED_RESERVATIONS_1",
        key + ":RESERVATION_SCHEMA",
    )
    ids, state_ids = [t["id"] for t in trades], [s["opportunity"]["id"] for s in states]
    need(
        len(ids) == len(set(ids)) and len(state_ids) == len(set(state_ids)),
        key + ":DUPLICATE_CAMPAIGN_OR_STATE",
    )
    state_map = {s["opportunity"]["id"]: s for s in states}
    nofill = report["modeledNoFills"]
    nofill_ids = [r["signalId"] for r in nofill]
    need(
        len(nofill_ids) == len(set(nofill_ids))
        and not set(ids).intersection(nofill_ids),
        key + ":NO_FILL_IDENTITIES",
    )
    need(
        len(records) == len(ids) + len(nofill_ids)
        and {r["id"] for r in records} == set(ids) | set(nofill_ids),
        key + ":RESERVATION_COVERAGE",
    )
    by_symbol = {s["symbol"]: s for s in dataset["series"]}
    by_known = {
        name: [b["availableAt"] for b in series["bars"]]
        for name, series in by_symbol.items()
    }
    costs_at = lambda at: (
        0
        if at < sessions[0]["open"]
        else daily_cost * (at // 86400000 - sessions[0]["open"] // 86400000 + 1)
    )

    def pnl_at(t, at):
        if at < t["opened"]:
            return 0.0
        if close_known(t) <= at:
            return t["netUsd"]
        marks = [m for m in t["marks"] if m["at"] <= at]
        if marks:
            return marks[-1]["pnl"]
        bars = by_symbol[t["symbol"]]["bars"]
        index = bisect.bisect_right(by_known[t["symbol"]], at) - 1
        need(index >= 0, key + ":UNOBSERVED_OPEN_POSITION_MARK")
        return (bars[index]["c"] - t["entry"]) * t["quantity"] - 2 * t["quantity"] * fee

    def cash_at(at):
        return (
            limits["capitalUsd"]
            + sum(t["netUsd"] for t in trades if close_known(t) <= at)
            + entitlement_total(trades, at, True)
            - costs_at(at)
        )

    total_exits = 0
    maximum_hold = 0.0
    for trade in trades:
        sid, quantity = trade["id"], trade["quantity"]
        need(
            sid in state_map
            and trade["symbol"] in universe
            and trade["direction"] == 1,
            key + ":CAMPAIGN_BINDING",
        )
        state = state_map[sid]
        need(
            state["status"] == "MODELED_CAMPAIGN"
            and state["opportunity"]["symbol"] == trade["symbol"],
            key + ":FILLED_STATE",
        )
        need(
            trade["opened"] == state["opportunity"]["plannedEntryAt"]
            and trade["opened"] >= state["opportunity"]["at"],
            key + ":ENTRY_TIMING",
        )
        opportunity = state["opportunity"]
        hours = opportunity.get("metadata", {}).get("roadmapHorizonHours", 72)
        need(hours in (24, 48, 72), key + ":REGISTERED_HORIZON")
        target = opportunity["at"] + hours * 3600000
        candidates = [s for s in dataset["sessions"] if s["open"] <= target]
        need(
            bool(candidates) and dataset["sessions"][-1]["close"] >= target,
            key + ":CALENDAR_COVERAGE",
        )
        deadline_session = candidates[-1]
        raw_deadline = min(target, deadline_session["close"] - 600000)
        expected_deadline = (
            deadline_session["open"]
            + ((raw_deadline - deadline_session["open"]) // 300000) * 300000
        )
        need(
            trade["holdingClockStartedAt"] == opportunity["at"]
            and trade["holdingDeadlineAt"] == expected_deadline
            and trade["closed"] <= expected_deadline,
            key + ":ORIGINAL_CALENDAR_DEADLINE",
        )
        if opportunity.get("metadata", {}).get("roadmapExit"):
            need(
                opportunity["metadata"]["roadmapOriginalDeadline"] == expected_deadline,
                key + ":H3_DEADLINE_RESET",
            )
        holding = (trade["closed"] - state["opportunity"]["at"]) / 3600000
        need(0 <= holding <= protocol["holding_maximum_hours"], key + ":HOLDING_LIMIT")
        maximum_hold = max(maximum_hold, holding)
        events = trade["inventoryEvents"]
        need(
            bool(events)
            and events[0]["kind"] == "ENTRY"
            and events[0]["at"] == trade["opened"]
            and events[-1]["at"] == trade["closed"]
            and events[0]["quantityDelta"] == quantity,
            key + ":INVENTORY_ENTRY_EXIT",
        )
        inventory, prior_time = 0, -1
        for event in events:
            q = event["quantityDelta"]
            need(
                type(q) is int
                and q != 0
                and event["at"] >= prior_time
                and event["knownAt"] >= event["at"],
                key + ":INVENTORY_CHRONOLOGY",
            )
            inventory += q
            need(0 <= inventory <= quantity, key + ":INVENTORY_UNITS")
            near(event["feeUsd"], abs(q) * fee, key + ":FEE_PER_SHARE")
            prior_time = event["at"]
        total_exits += len(events) - 1
        need(inventory == 0, key + ":TERMINAL_CAMPAIGN_INVENTORY")
        near(trade["feesUsd"], 2 * quantity * fee, key + ":ROUNDTRIP_FEE")
        expected = []
        for d in dataset["cashDividends"]:
            if (
                d["symbol"] != trade["symbol"]
                or not trade["opened"] < d["exAt"] <= trade["closed"]
            ):
                continue
            earlier = [e for e in events if e["at"] < d["exAt"]]
            need(
                all(e["knownAt"] <= d["exAt"] for e in earlier),
                key + ":EX_DATE_INVENTORY_KNOWLEDGE",
            )
            held = sum(e["quantityDelta"] for e in earlier)
            if held > 0:
                expected.append(
                    {
                        "dividendId": d["id"],
                        "campaignId": sid,
                        "symbol": trade["symbol"],
                        "exAt": d["exAt"],
                        "payableAt": d["payableAt"],
                        "quantity": held,
                        "amountPerShare": d["amountPerShare"],
                        "amountUsd": held * d["amountPerShare"],
                    }
                )
        need(
            trade["dividendEntitlements"] == expected,
            key + ":DIVIDEND_ENTITLEMENT_BINDING",
        )
        accrued = sum(d["amountUsd"] for d in expected)
        paid = sum(
            d["amountUsd"]
            for d in expected
            if d["payableAt"] is not None and d["payableAt"] <= trade["closed"]
        )
        for field, value in (
            ("dividendAccruedUsd", accrued),
            ("dividendPaidUsd", paid),
            ("dividendReceivableUsd", accrued - paid),
            ("netEconomicUsd", trade["netUsd"] + accrued),
        ):
            near(trade[field], value, key + ":" + field)
        receipt = state["fillBudgetReceipt"]
        need(
            receipt["status"] == "VERIFIED" and not receipt["breaches"],
            key + ":FILL_BUDGET_RECEIPT",
        )
        near(
            receipt["actualEntryNotionalUsd"],
            quantity * trade["entry"],
            key + ":ENTRY_NOTIONAL",
        )
        near(receipt["entryFeeUsd"], quantity * fee, key + ":ENTRY_FEE")
        plan = state["iocPlan"]
        need(
            trade["entry"] <= plan["priceCeiling"] + USD_ATOL, key + ":IOC_LIMIT_BREACH"
        )
        need(
            receipt["actualEntryNotionalUsd"]
            <= receipt["budgets"]["notionalBudgetUsd"] + USD_ATOL
            and receipt["modeledRiskUsd"]
            <= receipt["budgets"]["riskBudgetUsd"] + USD_ATOL
            and quantity * (trade["entry"] + fee)
            <= receipt["budgets"]["cashBudgetUsd"] + USD_ATOL,
            key + ":APPROVED_FILL_CAPACITY",
        )
    accepted: set[str] = set()
    record_map = {r["id"]: r for r in records}
    for state in states:
        sid, at = state["opportunity"]["id"], state["opportunity"]["at"]
        before = reservation_snapshot(records, accepted, at)
        audit_snapshot(state["reservationBefore"], before, key + ":BEFORE")
        accrued, paid = (
            entitlement_total(trades, at, False),
            entitlement_total(trades, at, True),
        )
        near(
            state["equity"],
            limits["capitalUsd"]
            + sum(pnl_at(t, at) for t in trades)
            + accrued
            - costs_at(at),
            key + ":DECISION_EQUITY",
        )
        for field, expected in (
            ("dividendAccruedUsd", accrued),
            ("dividendPaidUsd", paid),
            ("dividendReceivableUsd", accrued - paid),
            ("modeledExternalCostsAccruedUsd", costs_at(at)),
        ):
            near(state[field], expected, key + ":DECISION_" + field)
        if "cashPoolUsd" in state:
            near(state["cashPoolUsd"], cash_at(at), key + ":NO_EARLY_REINVESTMENT")
            near(
                state["cashBudgetUsd"],
                cash_at(at) - before["cashUsd"],
                key + ":AVAILABLE_CASH",
            )
        if state.get("reservationStatus") == "RESERVED":
            need(sid in record_map, key + ":MISSING_ACCEPTED_RESERVATION")
            record = record_map[sid]
            need(
                record["decisionAt"] == at and record["quantity"] == state["quantity"],
                key + ":RESERVATION_DECISION_BINDING",
            )
            need(
                record["riskUsd"] <= state["equity"] * limits["riskFraction"] + USD_ATOL
                and record["notionalUsd"]
                <= state["equity"] * limits["assetFraction"] + USD_ATOL,
                key + ":PER_ORDER_RESERVATION_CAPACITY",
            )
            accepted.add(sid)
        if "reservationAfter" in state:
            after = reservation_snapshot(records, accepted, at)
            audit_snapshot(state["reservationAfter"], after, key + ":AFTER")
            if state.get("reservationStatus") == "RESERVED":
                need(
                    after["riskUsd"]
                    <= state["equity"] * limits["openRiskFraction"] + USD_ATOL
                    and after["notionalUsd"]
                    <= state["equity"] * limits["grossFraction"] + USD_ATOL
                    and after["cashUsd"] <= cash_at(at) + USD_ATOL,
                    key + ":SHARED_CAPITAL_CAPACITY",
                )
    need(accepted == set(record_map), key + ":UNATTRIBUTED_RESERVATION")
    for record in records:
        observations = record["observations"]
        kinds = [o["kind"] for o in observations]
        need(
            kinds == (["OPENED", "CLOSED"] if record["id"] in ids else ["NO_FILL"]),
            key + ":RESERVATION_EVENT_SEQUENCE",
        )
        previous_at, previous_known = record["decisionAt"], record["decisionAt"]
        for o in observations:
            need(
                o["id"] == record["id"]
                and o["at"] >= previous_at
                and o["knownAt"] >= max(o["at"], previous_known),
                key + ":OBSERVATION_CHRONOLOGY",
            )
            previous_at, previous_known = o["at"], o["knownAt"]
        need(
            observations[-1]["remainingQuantity"]
            == observations[-1]["pendingQuantity"]
            == 0
            and observations[-1]["knownAt"] <= curve[-1]["end_at"],
            key + ":UNRESOLVED_TERMINAL_RESERVATION",
        )
    terminal = reservation_snapshot(records, accepted, curve[-1]["end_at"])
    need(not terminal["ids"], key + ":TERMINAL_EXPOSURE")
    for item in nofill:
        need(
            item["modeledOpeningFill"] > item["priceCeiling"]
            and item["positionOpened"] is False
            and item["resolutionAt"] >= item["decisionAt"]
            and item["modeledTradingPnlUsd"] == 0,
            key + ":NO_FILL_RECEIPT",
        )
    product = limits["capitalUsd"]
    for index, row in enumerate(curve):
        session_cost = costs_at(row["end_at"]) - costs_at(row["start_at"])
        start, end = row["equity_start_usd"], row["equity_end_usd"]
        near(
            start,
            curve[index - 1]["equity_end_usd"] if index else limits["capitalUsd"],
            key + ":CONTINUITY",
        )
        need(start > 0 and end > 0, key + ":INSOLVENCY")
        need(
            row["end_at"] == sessions[index]["close"]
            and row["start_at"]
            == (sessions[index - 1]["close"] if index else sessions[index]["open"] - 1),
            key + ":ROW_CLOCK",
        )
        near(
            row["portfolio_return"],
            end / start - 1,
            key + ":RETURN",
            tolerance=RETURN_ATOL,
        )
        near(
            row["portfolio_log_return"],
            math.log(end / start),
            key + ":LOG_RETURN",
            tolerance=RETURN_ATOL,
        )
        product *= 1 + row["portfolio_return"]
        need(set(row["asset_pnl_usd"]) == set(universe), key + ":ASSET_VECTOR")
        near(row["external_costs_usd"], session_cost, key + ":SESSION_COST")
        near(
            sum(row["asset_pnl_usd"].values()) - session_cost,
            end - start,
            key + ":ASSET_SUM_RECONCILIATION",
        )
        near(
            row["modeled_price_pnl_usd"]
            - row["modeled_trading_fees_usd"]
            + row["dividend_income_usd"]
            - session_cost,
            end - start,
            key + ":PRICE_FEES_DIVIDENDS_RECONCILIATION",
        )
        near(
            sum(row["asset_trading_pnl_usd"].values()),
            row["modeled_trading_pnl_usd"],
            key + ":ASSET_TRADING_SUM",
        )
        for symbol in universe:
            near(
                row["asset_pnl_usd"][symbol],
                row["asset_trading_pnl_usd"][symbol]
                + row["asset_dividend_income_usd"][symbol],
                key + ":ASSET_DIVIDEND_SUM",
            )
        at, prior = row["end_at"], row["start_at"]
        near(
            row["dividend_income_usd"],
            entitlement_total(trades, at, False)
            - entitlement_total(trades, prior, False),
            key + ":ACCRUAL_CLOCK",
        )
        near(
            row["dividend_cash_received_usd"],
            entitlement_total(trades, at, True)
            - entitlement_total(trades, prior, True),
            key + ":PAYMENT_CLOCK",
        )
        near(
            row["dividend_receivable_usd"],
            entitlement_total(trades, at, False) - entitlement_total(trades, at, True),
            key + ":RECEIVABLE",
        )
        near(row["conservative_cash_pool_usd"], cash_at(at), key + ":CLOSING_CASH")
    near(product, curve[-1]["equity_end_usd"], key + ":COMPOUND_RECONCILIATION")
    terminal_at = curve[-1]["end_at"]
    trading = sum(t["netUsd"] for t in trades)
    fees = sum(t["feesUsd"] for t in trades)
    accrued, paid = (
        entitlement_total(trades, terminal_at, False),
        entitlement_total(trades, terminal_at, True),
    )
    external = costs_at(terminal_at)
    net = curve[-1]["equity_end_usd"] - limits["capitalUsd"]
    accounting = report["accounting"]
    for field, expected in (
        ("modeledTradingPnlUsd", trading),
        ("modeledTradingFeesUsd", fees),
        ("modeledPricePnlUsd", trading + fees),
        ("dividendAccruedUsd", accrued),
        ("dividendPaidUsd", paid),
        ("dividendReceivableUsd", accrued - paid),
        ("modeledExternalCostsUsd", external),
        ("netEconomicUsd", net),
        ("terminalConservativeCashPoolUsd", cash_at(terminal_at)),
        ("reconciliationResidualUsd", 0),
    ):
        near(accounting[field], expected, key + ":ACCOUNTING_" + field)
    near(trading + accrued - external, net, key + ":TERMINAL_RECONCILIATION")
    near(report["portfolio"]["netUsd"], net, key + ":PORTFOLIO_NET")
    for name in ("VALIDATION", "TEST", "CONTINUOUS"):
        prefix = "evaluation" if name == "CONTINUOUS" else name.lower()
        rows = [
            r
            for r in curve
            if periods[prefix + "_start"] <= r["session_id"] <= periods[prefix + "_end"]
        ]
        summary = report["summary"][name]
        need(
            bool(rows)
            and summary["period"] == [rows[0]["session_id"], rows[-1]["session_id"]]
            and summary["sessions"] == len(rows),
            key + ":PHASE_PERIOD",
        )
        closed = [
            t for t in trades if rows[0]["start_at"] < t["closed"] <= rows[-1]["end_at"]
        ]
        for field, expected in (
            ("capital_at_phase_start", rows[0]["equity_start_usd"]),
            ("final_equity", rows[-1]["equity_end_usd"]),
            (
                "economic_pnl_modeled_usd",
                rows[-1]["equity_end_usd"] - rows[0]["equity_start_usd"],
            ),
            (
                "total_return_fraction",
                rows[-1]["equity_end_usd"] / rows[0]["equity_start_usd"] - 1,
            ),
            ("external_costs_modeled_usd", sum(r["external_costs_usd"] for r in rows)),
            ("dividend_income_usd", sum(r["dividend_income_usd"] for r in rows)),
            ("closed_campaigns", len(closed)),
            ("closed_campaign_trading_pnl_usd", sum(t["netUsd"] for t in closed)),
        ):
            near(summary[field], expected, key + ":SUMMARY_" + field)
        for field, at in (
            ("positions_carried_in", rows[0]["start_at"]),
            ("positions_carried_out", rows[-1]["end_at"]),
        ):
            near(
                summary[field],
                sum(t["opened"] <= at < t["closed"] for t in trades),
                key + ":PHASE_CARRY",
            )
        for symbol in universe:
            near(
                summary["contribution_by_asset_usd"][symbol],
                sum(r["asset_pnl_usd"][symbol] for r in rows),
                key + ":SUMMARY_ASSET",
            )
        near(summary["contribution_residual_usd"], 0, key + ":SUMMARY_RESIDUAL")
        need(summary["real_profitability"] is None, key + ":REAL_PROFITABILITY_CLAIM")
    near(
        report["summary"]["TEST"]["capital_at_phase_start"],
        report["summary"]["VALIDATION"]["final_equity"],
        key + ":VALIDATION_TEST_CARRY",
    )
    requested = sum(r["quantity"] for r in records)
    executed = sum(t["quantity"] for t in trades)
    execution = report["summary"]["execution"]
    for field, expected in (
        ("orders_placed_modeled", len(records)),
        ("filled_campaigns", len(trades)),
        ("requested_shares_modeled", requested),
        ("filled_shares_modeled", executed),
        ("pending_or_open_terminal", 0),
    ):
        near(execution[field], expected, key + ":EXECUTION_COUNT")
    if requested:
        near(
            execution["fill_ratio_modeled"],
            executed / requested,
            key + ":FILL_RATIO",
            tolerance=RETURN_ATOL,
        )
    else:
        need(execution["fill_ratio_modeled"] is None, key + ":EMPTY_FILL_RATIO")
    need(execution["real_fill_ratio"] is None, key + ":REAL_FILL_CLAIM")
    return {
        "verified": True,
        "sessions": len(curve),
        "initial_equity": limits["capitalUsd"],
        "final_equity": curve[-1]["equity_end_usd"],
        "net_economic_modeled_usd": net,
        "closed_campaigns": len(trades),
        "partial_or_final_exit_events": total_exits,
        "modeled_no_fills": len(nofill),
        "requested_shares": requested,
        "executed_shares": executed,
        "modeled_fill_ratio": executed / requested if requested else None,
        "modeled_trading_fees_usd": fees,
        "modeled_external_costs_usd": external,
        "dividend_accrued_usd": accrued,
        "dividend_paid_usd": paid,
        "dividend_receivable_usd": accrued - paid,
        "maximum_holding_hours_from_decision": maximum_hold,
        "terminal_reservations": len(terminal["ids"]),
        "test_initial_equity": report["summary"]["TEST"]["capital_at_phase_start"],
        "test_net_economic_modeled_usd": report["summary"]["TEST"][
            "economic_pnl_modeled_usd"
        ],
        "real_fill_ratio": None,
        "fill_ratio_scope": "Only submitted modeled orders, after admissions/refusals. A modeled opening within the IOC ceiling fills its whole quantity; OHLCV supplies no empirical queue or executable-size evidence.",
    }
