"""Synthetic software contracts for whole-account forward accounting.

No fixture is a broker record or investment experiment. The verified-view
fixtures exercise the pure consumer after the independent ledger verifier;
orchestration mocks are used only to test gates, never to certify evidence.
"""
from __future__ import annotations

import copy
import importlib.util
import math
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / "quant"))

from harpoon_quant.forward_economics import (
    bootstrap_forward_growth,
    epoch,
    summarize_observed_portfolio,
)


START = int(datetime(2026, 10, 15, 13, 30, tzinfo=UTC).timestamp() * 1000)
MINUTE = 60_000


def iso(at: int) -> str:
    return datetime.fromtimestamp(at / 1000, UTC).isoformat()


def protocol() -> dict:
    return {
        "schema": "HARPOON_ECONOMIC_PROTOCOL_2",
        "initial_equity_usd": 100,
        "universe": ["SPY", "AAA"],
        "period": {"test_start": iso(START), "test_end": iso(START + 2 * MINUTE)},
        "evaluation_sessions": [
            {"session_id": "synthetic-interval-1", "start_at": iso(START), "end_at": iso(START + MINUTE)},
            {"session_id": "synthetic-interval-2", "start_at": iso(START + MINUTE), "end_at": iso(START + 2 * MINUTE)},
        ],
        "forward_validation": {
            "schema": "HARPOON_FORWARD_SPEC_1",
            "boundary_tolerance_ms": 0,
            "maximum_observation_gap_ms": MINUTE,
            "family_alpha": 0.025,
            "minimum_economic_pnl_usd": 0,
            "minimum_mean_log_growth": 0,
        },
        "dependence": {"block_lengths": [2, 4], "minimum_sessions": 8, "minimum_complete_blocks": 2},
        "statistics": {"family_alpha": 0.025, "bootstrap_repetitions": 40_000,
                       "minimum_tail_draws": 20, "seed": 293},
        "search": {"total_attempts": 23, "counter_reset": False},
        "max_drawdown_fraction": 0.08,
        "max_gross_exposure_fraction": 0.5,
        "horizon_hours": 72,
    }


def ledger_view(equities=(100, 110, 121), costs=(0, 1, 2), *, flows=(0, 0, 0),
                returns=None, times=None, positions=None) -> dict:
    """Manufacture a small verified-view *test double*, not verification proof."""
    times = times if times is not None else [START + i * MINUTE for i in range(len(equities))]
    positions = positions if positions is not None else [[] for _ in equities]
    economic = [e - c for e, c in zip(equities, costs, strict=True)]
    if returns is None:
        if any(flows):
            raise AssertionError("Flow fixtures require independently specified time-weighted returns")
        returns = [None] + [b / a - 1 if a > 0 and b >= 0 else None for a, b in zip(economic, economic[1:])]
    rows = []
    for index, (at, equity, cost, flow, value, rate, inventory) in enumerate(
        zip(times, equities, costs, flows, economic, returns, positions, strict=True)
    ):
        rows.append({"at": at, "equity": equity, "economicEquity": value,
                     "cumulativeExternalCostUsd": cost, "cumulativeExternalFlowUsd": flow,
                     "economicReturn": rate, "positions": copy.deepcopy(inventory),
                     "preFlowMarks": [], "economicKnownAt": at,
                     "sourceReceipt": {"nature": "SYNTHETIC_ENGINEERING_ONLY", "row": index}})
    return {
        "verified": True,
        "from": times[0],
        "through": times[-1],
        "state": {"reconciled": True, "economicRestatementRequired": False,
                  "costCoverage": {"from": times[0], "through": times[-1], "known_at": times[-1]},
                  "closedEconomic": {"from": times[0], "through": times[-1]},
                  "insolvency": {"account": False, "economic": False}},
        "observations": rows,
        "activities": [],
        "externalCosts": [{"id": "synthetic-expense-" + str(i), "at": at,
                           "amount_usd": amount - (costs[i - 1] if i else 0), "already_in_account": False}
                          for i, (at, amount) in enumerate(zip(times, costs, strict=True))
                          if amount - (costs[i - 1] if i else 0) > 0],
        "closedBrokerAccruals": {"verified": True, "comparedFrom": times[0], "comparedThrough": times[-1]},
        "sourceAuthenticityVerified": False,
        "financialAdvantageDemonstrated": False,
        "authorizesOrders": False,
    }


def flow_view() -> dict:
    # Deposit: 100 -> 110 before deposit -> 210 after -> 232 NAV minus 1 cost = 231.
    # Withdrawal: 232 NAV -> 132 after withdrawal, net economic capital 131;
    # terminal 146.1 NAV minus cumulative 2 cost = 144.1. TWR = 1.21 * 1.1 - 1.
    view = ledger_view((100, 232, 146.1), (0, 1, 2), flows=(0, 100, 0), returns=(None, 0.21, 0.1))
    for row, identifier, amount, before, after, at in (
        (view["observations"][1], "synthetic-deposit", 100, 110, 210, START + MINUTE // 2),
        (view["observations"][2], "synthetic-withdrawal", -100, 232, 132, START + MINUTE + MINUTE // 2),
    ):
        view["activities"].append({"id": identifier, "at": at, "knownAt": row["at"],
                                   "classification": "EXTERNAL_FLOW", "baselineIncluded": False,
                                   "cashDeltaUsd": amount, "timePrecision": "INSTANT"})
        row["preFlowMarks"] = [{"activityId": identifier, "at": at, "known_at": row["at"],
                                "equityBefore": before, "equityAfter": after}]
    return view


class ObservedPortfolioTests(unittest.TestCase):
    def test_external_costs_reduce_net_result_and_compound_whole_account(self) -> None:
        view = ledger_view()
        original = copy.deepcopy(view)
        out = summarize_observed_portfolio(view, protocol())
        self.assertEqual(out["account_pnl_usd"], 21)
        self.assertEqual(out["external_costs_usd"], 2)
        self.assertEqual(out["economic_pnl_usd"], 19)
        self.assertAlmostEqual(out["economic_compounded_return"], 0.19)
        self.assertAlmostEqual(math.exp(sum(out["log_returns"])), 1.19)
        self.assertEqual(out["capital_resets"], 0)
        self.assertEqual(view, original, "Summarization must not rewrite source account evidence")

    def test_plus_ten_minus_ten_is_a_loss_without_capital_reset(self) -> None:
        out = summarize_observed_portfolio(ledger_view((100, 110, 99), (0, 0, 0)), protocol())
        self.assertEqual(out["economic_pnl_usd"], -1)
        self.assertAlmostEqual(out["economic_compounded_return"], -0.01)
        self.assertAlmostEqual(out["economic_unit_curve"][-1]["economic_units"], 0.99)
        self.assertAlmostEqual(out["economic_drawdown_fraction_observed"], 0.1)

    def test_deposit_and_withdrawal_use_preverified_twr_not_capital_as_profit(self) -> None:
        out = summarize_observed_portfolio(flow_view(), protocol())
        self.assertEqual(out["net_external_flows_usd"], 0)
        self.assertEqual(out["external_flow_event_count"], 2)
        self.assertAlmostEqual(out["account_pnl_usd"], 46.1)
        self.assertAlmostEqual(out["economic_pnl_usd"], 44.1)
        self.assertAlmostEqual(out["economic_compounded_return"], 0.331)
        self.assertNotAlmostEqual(out["economic_compounded_return"], out["economic_pnl_usd"] / 100)

    def test_flow_without_valuation_is_not_given_an_invented_return(self) -> None:
        view = flow_view()
        view["observations"][1]["economicReturn"] = None
        view["observations"][1]["preFlowMarks"] = []
        with self.assertRaisesRegex(ValueError, "INVALID_FORWARD_ECONOMIC_RETURN"):
            summarize_observed_portfolio(view, protocol())

    def test_a_single_losing_asset_does_not_reject_positive_portfolio_compound(self) -> None:
        positions = [[{"symbol": "SPY", "marketValueUsd": spy, "quantity": 1},
                      {"symbol": "AAA", "marketValueUsd": stock, "quantity": 1}]
                     for spy, stock in ((50, 30), (45, 37), (40, 45))]
        out = summarize_observed_portfolio(ledger_view((100, 102, 105), (0, 0, 0), positions=positions), protocol())
        self.assertEqual(out["economic_pnl_usd"], 5)
        self.assertAlmostEqual(out["economic_compounded_return"], 0.05)
        self.assertFalse(out["individual_asset_profit_required"])
        self.assertEqual(out["terminal_positions"], positions[-1], "Open inventory cannot be closed synthetically")

    def test_intraperiod_loss_and_gross_short_exposure_survive_profitable_terminal_mark(self) -> None:
        positions = [[], [{"symbol": "SPY", "marketValueUsd": 20}, {"symbol": "AAA", "marketValueUsd": -40}], []]
        out = summarize_observed_portfolio(ledger_view((100, 60, 105), (0, 0, 0), positions=positions), protocol())
        self.assertEqual(out["economic_pnl_usd"], 5)
        self.assertAlmostEqual(out["economic_drawdown_fraction_observed"], 0.4)
        self.assertEqual(out["maximum_gross_exposure_fraction_observed"], 1)

    def test_nonzero_costs_at_period_start_are_not_subtracted_twice(self) -> None:
        out = summarize_observed_portfolio(ledger_view((100, 111, 123), (2, 3, 5)), protocol())
        self.assertEqual(out["initial_economic_equity_usd"], 98)
        self.assertEqual(out["external_costs_usd"], 3)
        self.assertEqual(out["economic_pnl_usd"], 20)
        self.assertAlmostEqual(out["economic_compounded_return"], 118 / 98 - 1)

    def test_insolvency_is_sticky_despite_recapitalization_and_recovery(self) -> None:
        view = ledger_view((100, 0, 125), (0, 0, 0), flows=(0, 0, 125), returns=(None, -1, None))
        view["state"]["insolvency"] = {"account": True, "economic": True}
        out = summarize_observed_portfolio(view, protocol())
        self.assertTrue(out["insolvency"])
        self.assertEqual(out["final_account_equity_usd"], 125)
        self.assertEqual(out["economic_pnl_usd"], -100)
        self.assertIsNone(out["economic_compounded_return"])
        self.assertEqual(out["economic_drawdown_fraction_observed"], 1)
        self.assertEqual(out["log_returns"], [])

    def test_external_expense_can_cause_economic_insolvency_with_positive_broker_nav(self) -> None:
        view = ledger_view((100, 1, 2), (0, 2, 2), returns=(None, None, None))
        out = summarize_observed_portfolio(view, protocol())
        self.assertTrue(out["insolvency"])
        self.assertEqual(out["final_account_equity_usd"], 2)
        self.assertEqual(out["final_economic_equity_usd"], 0)
        self.assertEqual(out["economic_pnl_usd"], -100)
        self.assertIsNone(out["economic_compounded_return"])

    def test_preflow_insolvency_cannot_be_hidden_inside_a_positive_nav_interval(self) -> None:
        view = ledger_view((100, 110, 121), (0, 0, 0), flows=(0, 100, 100), returns=(None, -1, 0.1))
        view["state"]["insolvency"] = {"account": True, "economic": True}
        at = START + MINUTE // 2
        view["observations"][1]["preFlowMarks"] = [{"activityId": "rescue", "at": at,
                                                   "known_at": START + MINUTE,
                                                   "equityBefore": 0, "equityAfter": 100}]
        view["activities"] = [{"id": "rescue", "at": at, "classification": "EXTERNAL_FLOW",
                               "baselineIncluded": False, "cashDeltaUsd": 100}]
        out = summarize_observed_portfolio(view, protocol())
        self.assertTrue(out["insolvency"])
        self.assertIsNone(out["economic_compounded_return"])
        self.assertEqual(out["economic_drawdown_fraction_observed"], 1)
        self.assertEqual(out["economic_pnl_usd"], -79)

    def test_preflow_loss_remains_in_drawdown_even_when_both_endpoint_returns_are_positive(self) -> None:
        view = ledger_view((100, 1210, 1331), (0, 0, 0), flows=(0, 100, 100), returns=(None, 0.1, 0.1))
        at = START + MINUTE // 2
        view["observations"][1]["preFlowMarks"] = [{"activityId": "deposit-after-loss", "at": at,
                                                   "known_at": START + MINUTE,
                                                   "equityBefore": 10, "equityAfter": 110}]
        view["activities"] = [{"id": "deposit-after-loss", "at": at, "classification": "EXTERNAL_FLOW",
                               "baselineIncluded": False, "cashDeltaUsd": 100}]
        out = summarize_observed_portfolio(view, protocol())
        self.assertFalse(out["insolvency"])
        self.assertAlmostEqual(out["economic_compounded_return"], 0.21)
        self.assertAlmostEqual(out["economic_drawdown_fraction_observed"], 0.9)
        self.assertTrue(any(row["at"] == at and abs(row["economic_units"] - 0.1) < 1e-12
                            for row in out["economic_unit_curve"]))

    def test_late_marks_use_observed_times_within_declared_tolerance(self) -> None:
        p = protocol()
        p["forward_validation"]["boundary_tolerance_ms"] = 25
        out = summarize_observed_portfolio(ledger_view(times=[START + i * MINUTE + 25 for i in range(3)]), p)
        self.assertEqual(out["period_requested"], {"start_at": START, "end_at": START + 2 * MINUTE})
        self.assertEqual(out["period_effective"], {"start_at": START + 25, "end_at": START + 2 * MINUTE + 25})
        self.assertEqual(out["session_returns"][0]["effective_end_at"], START + MINUTE + 25)
        self.assertAlmostEqual(out["economic_compounded_return"], 0.19)

    def test_early_observation_is_not_reused_as_a_missing_boundary(self) -> None:
        view = ledger_view(times=[START - 1, START + MINUTE, START + 2 * MINUTE])
        with self.assertRaisesRegex(ValueError, "FORWARD_BOUNDARY_MARK_TOO_LATE"):
            summarize_observed_portfolio(view, protocol())
        view = ledger_view(times=[START, START + MINUTE, START + 2 * MINUTE - 1])
        with self.assertRaisesRegex(ValueError, "FORWARD_BOUNDARY_MARK_MISSING"):
            summarize_observed_portfolio(view, protocol())

    def test_tolerance_is_not_widened_after_late_data(self) -> None:
        p = protocol()
        p["forward_validation"]["boundary_tolerance_ms"] = 25
        with self.assertRaisesRegex(ValueError, "FORWARD_BOUNDARY_MARK_TOO_LATE"):
            summarize_observed_portfolio(ledger_view(times=[START, START + MINUTE, START + 2 * MINUTE + 26]), p)

    def test_missing_observation_cannot_skip_risk_or_compound_periods(self) -> None:
        view = ledger_view()
        view["observations"].pop(1)
        with self.assertRaisesRegex(ValueError, "FORWARD_OBSERVATION_GAP"):
            summarize_observed_portfolio(view, protocol())

    def test_duplicate_or_reversed_observation_time_is_rejected(self) -> None:
        for at in (START, START - 1):
            with self.subTest(at=at):
                view = ledger_view()
                view["observations"][1]["at"] = at
                with self.assertRaisesRegex(ValueError, "FORWARD_OBSERVATION_CHRONOLOGY"):
                    summarize_observed_portfolio(view, protocol())

    def test_missing_cost_is_unknown_and_never_zero(self) -> None:
        for key in ("cumulativeExternalCostUsd", "economicEquity"):
            with self.subTest(key=key):
                view = ledger_view()
                view["observations"][-1][key] = None
                with self.assertRaisesRegex(ValueError, "INVALID_FORWARD_"):
                    summarize_observed_portfolio(view, protocol())
        view = ledger_view()
        view["observations"][-1]["economicEquity"] = view["observations"][-1]["equity"]
        with self.assertRaisesRegex(ValueError, "FORWARD_ECONOMIC_EQUITY_IDENTITY"):
            summarize_observed_portfolio(view, protocol())

    def test_cost_and_broker_accrual_coverage_must_span_the_effective_window(self) -> None:
        for parent, field, value, code in (
            ("costCoverage", "from", START + 1, "FORWARD_COST_COVERAGE_INCOMPLETE"),
            ("costCoverage", "through", START + 2 * MINUTE - 1, "FORWARD_COST_COVERAGE_INCOMPLETE"),
            ("closedEconomic", "through", START + MINUTE, "FORWARD_CLOSED_ECONOMIC_PREFIX_INCOMPLETE"),
            ("closedBrokerAccruals", "verified", False, "FORWARD_BROKER_ACCRUAL_COVERAGE"),
            ("closedBrokerAccruals", "comparedThrough", START + MINUTE, "FORWARD_BROKER_ACCRUAL_COVERAGE"),
        ):
            with self.subTest(parent=parent, field=field):
                view = ledger_view()
                target = view[parent] if parent == "closedBrokerAccruals" else view["state"][parent]
                target[field] = value
                with self.assertRaisesRegex(ValueError, code):
                    summarize_observed_portfolio(view, protocol())

    def test_unverified_or_restatement_account_cannot_be_summarized_as_closed(self) -> None:
        view = ledger_view()
        view["verified"] = False
        with self.assertRaisesRegex(ValueError, "REEXECUTED_LEDGER_REQUIRED"):
            summarize_observed_portfolio(view, protocol())
        view = ledger_view()
        view["state"]["economicRestatementRequired"] = True
        with self.assertRaisesRegex(ValueError, "FORWARD_LEDGER_RECONCILIATION_OR_RESTATEMENT"):
            summarize_observed_portfolio(view, protocol())

    def test_calendar_must_reach_final_mark_without_boundary_collision(self) -> None:
        p = protocol()
        p["evaluation_sessions"].pop()
        with self.assertRaisesRegex(ValueError, "FORWARD_CALENDAR_DOES_NOT_REACH_TERMINAL_MARK"):
            summarize_observed_portfolio(ledger_view(), p)
        p = protocol()
        p["evaluation_sessions"][1]["end_at"] = p["evaluation_sessions"][0]["end_at"]
        with self.assertRaisesRegex(ValueError, "FORWARD_SESSION_BOUNDARY_COLLISION"):
            summarize_observed_portfolio(ledger_view(), p)

    def test_initial_capital_universe_and_clock_limits_are_enforced(self) -> None:
        p = protocol()
        p["initial_equity_usd"] = 101
        with self.assertRaisesRegex(ValueError, "FORWARD_INITIAL_CAPITAL_NOT_COMPARABLE"):
            summarize_observed_portfolio(ledger_view(), p)
        view = ledger_view()
        view["observations"][-1]["positions"] = [{"symbol": "UNDECLARED", "marketValueUsd": 1}]
        with self.assertRaisesRegex(ValueError, "FORWARD_UNIVERSE_MISMATCH"):
            summarize_observed_portfolio(view, protocol())
        for key, value, code in (("boundary_tolerance_ms", 90_001, "FORWARD_BOUNDARY_TOLERANCE"),
                                 ("maximum_observation_gap_ms", 0, "FORWARD_OBSERVATION_GAP_LIMIT")):
            p = protocol()
            p["forward_validation"][key] = value
            with self.assertRaisesRegex(ValueError, code):
                summarize_observed_portfolio(ledger_view(), p)
        with self.assertRaisesRegex(ValueError, "UTC_OFFSET_REQUIRED"):
            epoch("2026-10-15T13:30:00")


class ForwardBootstrapTests(unittest.TestCase):
    DATA = [0.01, 0.02, 0.015, 0.005, 0.012, 0.017, 0.008, 0.011]

    def test_computation_is_reproducible_and_does_not_create_extra_evidence(self) -> None:
        first = bootstrap_forward_growth(self.DATA, protocol())
        self.assertEqual(first, bootstrap_forward_growth(self.DATA, protocol()))
        self.assertEqual(first["status"], "COMPUTED")
        self.assertEqual(first["observed_sessions"], len(self.DATA))
        self.assertEqual(first["unit"], "JOINT_ACCOUNT_SESSION")
        self.assertEqual(first["historical_search_attempts_used"], 23)
        self.assertEqual([b["length_sessions"] for b in first["blocks"]], [2, 4])
        self.assertAlmostEqual(first["one_sided_tail"], 0.025 / (23 * 2))
        self.assertAlmostEqual(first["point_mean_log_growth"], sum(self.DATA) / len(self.DATA))
        for block in first["blocks"]:
            self.assertLessEqual(block["lower_one_sided_mean_log_growth"], block["upper_diagnostic"])
            self.assertGreaterEqual(block["lower_one_sided_mean_log_growth"], min(self.DATA))
            self.assertLessEqual(block["upper_diagnostic"], max(self.DATA))
        self.assertIsNone(first["future_profit_probability"])
        self.assertIsNone(first["effective_independent_observations"])
        self.assertFalse(first["coverage_guarantee"])

    def test_small_and_constant_sample_is_inconclusive_even_when_positive(self) -> None:
        out = bootstrap_forward_growth([0.01], protocol())
        self.assertEqual(out["status"], "INCONCLUSIVE")
        self.assertIn("FORWARD_SESSION_SAMPLE_INSUFFICIENT", out["reasons"])
        self.assertIn("FORWARD_DEPENDENCE_BLOCKS_INSUFFICIENT", out["reasons"])
        self.assertIn("FORWARD_DEGENERATE_RETURN_VARIANCE", out["reasons"])
        self.assertEqual(out["blocks"], [])
        self.assertGreater(out["point_mean_log_growth"], 0)

    def test_tail_resolution_is_checked_after_search_and_block_correction(self) -> None:
        p = protocol()
        p["statistics"]["bootstrap_repetitions"] = 100
        out = bootstrap_forward_growth(self.DATA, p)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        self.assertIn("FORWARD_BOOTSTRAP_TAIL_RESOLUTION_INSUFFICIENT", out["reasons"])
        self.assertEqual(out["blocks"], [])

    def test_dependence_blocks_need_actual_observed_sessions(self) -> None:
        p = protocol()
        p["dependence"]["block_lengths"] = [2, 5]
        out = bootstrap_forward_growth(self.DATA, p)
        self.assertIn("FORWARD_DEPENDENCE_BLOCKS_INSUFFICIENT", out["reasons"])
        self.assertEqual(out["observed_sessions"], 8)

    def test_zero_or_negative_growth_is_not_converted_into_positive_result(self) -> None:
        out = bootstrap_forward_growth([-x for x in self.DATA], protocol())
        self.assertEqual(out["status"], "COMPUTED")
        self.assertLess(out["point_mean_log_growth"], 0)
        self.assertTrue(all(b["upper_diagnostic"] < 0 for b in out["blocks"]))
        flat = bootstrap_forward_growth([0.0] * 8, protocol())
        self.assertIn("FORWARD_DEGENERATE_RETURN_VARIANCE", flat["reasons"])

    def test_joint_alpha_and_historical_attempt_budget_cannot_be_reset(self) -> None:
        p = protocol()
        p["forward_validation"]["family_alpha"] = 0.03
        with self.assertRaisesRegex(ValueError, "COMBINED_COMPARISON_FORWARD_ALPHA_EXCEEDS_005"):
            bootstrap_forward_growth(self.DATA, p)
        for key, value in (("total_attempts", 22), ("total_attempts", True), ("counter_reset", True)):
            with self.subTest(key=key, value=value):
                p = protocol()
                p["search"][key] = value
                with self.assertRaisesRegex(ValueError, "FORWARD_SEARCH_HISTORY_NOT_RECONCILED"):
                    bootstrap_forward_growth(self.DATA, p)

    def test_nonfinite_empty_and_multidimensional_return_samples_are_rejected(self) -> None:
        for values in ([], [math.nan], [math.inf], [-math.inf], [[0.01], [0.02]]):
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, "FORWARD_FINITE_LOG_RETURNS"):
                    bootstrap_forward_growth(values, protocol())

    def test_compute_budget_fails_before_random_resampling(self) -> None:
        p = protocol()
        p["statistics"]["bootstrap_repetitions"] = 500_000
        with patch("harpoon_quant.forward_economics.np.random.default_rng") as rng:
            out = bootstrap_forward_growth(self.DATA * 150, p)
            self.assertIn("FORWARD_BOOTSTRAP_COMPUTE_BUDGET_EXCEEDED", out["reasons"])
            self.assertEqual(out["blocks"], [])
            rng.assert_not_called()

    def test_invalid_resampling_declarations_are_rejected(self) -> None:
        for lengths in ([], [2, 2], [True], [0], [20_001]):
            with self.subTest(lengths=lengths):
                p = protocol()
                p["dependence"]["block_lengths"] = lengths
                with self.assertRaisesRegex(ValueError, "FORWARD_BLOCK_LENGTHS"):
                    bootstrap_forward_growth(self.DATA, p)
        for count in (99, 500_001, True, 100.5):
            with self.subTest(count=count):
                p = protocol()
                p["statistics"]["bootstrap_repetitions"] = count
                with self.assertRaisesRegex(ValueError, "FORWARD_BOOTSTRAP_REPETITIONS"):
                    bootstrap_forward_growth(self.DATA, p)


class Level7WorkflowScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("level7_workflow_test_target", APP / "tools/level7_workflow.py")
        cls.workflow = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.workflow)

    def test_missing_resources_are_individual_blockers_not_zero_cost_profit(self) -> None:
        out = self.workflow.evaluate({"schema": self.workflow.SCHEMA, "target": 7}, APP)
        self.assertFalse(out["level7_criterion_met"])
        self.assertIsNone(out["economic_score"])
        self.assertIsNone(out["observed_portfolio"])
        self.assertIn("CAUSAL_PANEL_REQUEST_MISSING", out["blockers"])
        self.assertIn("ECONOMIC_PROTOCOL_MISSING", out["blockers"])
        self.assertIn("ECONOMIC_EVIDENCE_MISSING", out["blockers"])
        self.assertIn("FORWARD_ATTRIBUTION_REQUEST_MISSING", out["blockers"])
        for name in ("execution_allowed", "liveApproved", "deployment_allowed", "financial_approval"):
            self.assertFalse(out[name])
        self.assertEqual(out["research_trials_created"], 0)
        self.assertEqual(out["models_fitted"], 0)

    def test_changed_source_hash_cannot_enter_the_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "panel.json").write_text("{}", encoding="utf-8")
            out = self.workflow.evaluate({"schema": self.workflow.SCHEMA, "target": 7,
                                          "panel_request": {"path": "panel.json", "sha256": "0" * 64}}, base)
        self.assertTrue(any("SOURCE_HASH_MISMATCH" in code for code in out["blockers"]))
        self.assertFalse(out["level7_criterion_met"])

    def mocked_orchestration(self, ledger: dict, nature: str) -> dict:
        # These mocks isolate gate wiring. They do not run/relabel a financial study.
        p = protocol()
        values = {"panel": {}, "protocol": p, "evidence": {"generated_at": "2026-01-01T00:00:00Z"}, "forward": {}}
        panel = {"panel": {"origin": "OBSERVED"}, "artifact_hash": "synthetic-panel-binding",
                 "readiness": {"status": "PANEL_ADMISSIBLE_NOT_FINANCIALLY_VALIDATED", "accepted_rows": 100}}
        gate = {"level5_criterion_met": True, "dictamen": "CANDIDATO_PARA_VALIDACION_FORWARD",
                "derivation": {"readiness": {"components": {"data": {"artifact_hash": "synthetic-panel-binding"}}}}}
        forward = {"verified": True, "executionNature": nature, "ledger": ledger,
                   "risk": {"maximum_observed_holding_hours": 0}}
        stats = {"status": "COMPUTED", "point_mean_log_growth": 0.01,
                 "blocks": [{"lower_one_sided_mean_log_growth": 0.001}]}
        request = {"schema": self.workflow.SCHEMA, "target": 7,
                   "panel_request": {"path": "panel"}, "economic_protocol": {"path": "protocol"},
                   "economic_evidence": {"path": "evidence"}, "forward_attribution_request": {"path": "forward"}}
        with patch.object(self.workflow, "load_ref", side_effect=lambda ref, base, sources: (copy.deepcopy(values[ref["path"]]), APP / "synthetic.json")), \
             patch("harpoon_quant.causal_panel.build", return_value=panel), \
             patch("harpoon_quant.economic_gate_v2.evaluate", return_value=gate), \
             patch.object(self.workflow, "validate_forward_spec", return_value={}), \
             patch.object(self.workflow, "node_attribution", return_value=forward), \
             patch.object(self.workflow, "bootstrap_forward_growth", return_value=stats):
            return self.workflow.evaluate(request, APP)

    def test_net_zero_external_flows_still_block_cash_only_comparison(self) -> None:
        out = self.mocked_orchestration(flow_view(), "REAL")
        self.assertAlmostEqual(out["observed_portfolio"]["economic_compounded_return"], 0.331)
        self.assertEqual(out["observed_portfolio"]["net_external_flows_usd"], 0)
        self.assertIn("FORWARD_FLOWS_OUTSIDE_COMPARISON_SCOPE", out["blockers"])
        self.assertFalse(out["level7_criterion_met"])
        self.assertIsNone(out["economic_score"])

    def test_positive_paper_result_does_not_certify_real_profitability(self) -> None:
        out = self.mocked_orchestration(ledger_view(), "PAPER")
        self.assertGreater(out["observed_portfolio"]["economic_pnl_usd"], 0)
        self.assertIn("REAL_FORWARD_EXECUTION_REQUIRED", out["blockers"])
        self.assertFalse(out["level7_criterion_met"])
        self.assertIsNone(out["economic_score"])


if __name__ == "__main__":
    unittest.main()
