"""Synthetic software tests. They do not establish a market advantage."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from harpoon_quant.calibration import fit
from harpoon_quant.core import FEATURES, Config, digest, timestamp
from harpoon_quant.paired_replay import (
    SCHEMA,
    calibration_readiness,
    readiness,
    reconcile_replay,
    run_paired_replay,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "paired_svr_fixture", ROOT / "examples/svr/make_fixture.py"
)
assert SPEC is not None and SPEC.loader is not None
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class PairedReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = FIXTURE.build_fixture()
        cls.svr = fit(
            cls.fixture["data"],
            cls.fixture["available_at"],
            Config(**cls.fixture["config"]),
            estimator="svr",
        )
        cls.ridge = {
            "schema": "HARPOON_QUANT_CALIBRATION_1",
            "origin": "SYNTHETIC_ENGINEERING_ONLY",
            "available_at": cls.fixture["available_at"],
            "horizon_hours": 24,
            "feature_names": list(FEATURES),
            "models": {
                "SYNTHSVR": {
                    "accepted": True,
                    "mean": [0] * 8,
                    "scale": [1] * 8,
                    "beta": [0.03] + [0] * 8,
                    "residuals": {
                        f"2026-09-{d:02d}": (d % 3 - 1) * 0.0001 for d in range(1, 26)
                    },
                }
            },
        }

    def data(self):
        asset = {
            "book": "equity",
            "factor": "SYNTHETIC_FACTOR",
            "leverage": 1,
            "multiplier": 1,
            "step": 1,
            "minQty": 1,
            "tick": 0.01,
        }
        frames = []
        for i, hour in enumerate(("13:50", "14:30", "18:45")):
            at = f"2026-10-15T{hour}:00+00:00"
            ex = (timestamp(at) + timedelta(seconds=1)).isoformat()
            quote = {"bid": 100.0, "ask": 101.0, "at": at, "known_at": at}
            frames.append(
                {
                    "decision_id": f"D{i}",
                    "at": at,
                    "session": "2026-10-15",
                    "open": "2026-10-15T13:30:00+00:00",
                    "close": "2026-10-15T20:00:00+00:00",
                    "external_flow_before_usd": 0,
                    "operating_costs_usd": {"C0": 0, "RIDGE": 0, "SVR": 0},
                    "opportunities": [
                        {
                            "id": "PLUGIN|SYNTHSVR",
                            "symbol": "SYNTHSVR",
                            "features": FIXTURE.vector(0.9, 0.7),
                            "features_known_at": at,
                            "max_qty": 2,
                        }
                    ],
                    "quotes": {"SYNTHSVR": quote},
                    "execution": {
                        "at": ex,
                        "quotes": {
                            "SYNTHSVR": {
                                **quote,
                                "at": ex,
                                "known_at": ex,
                                "bid_size": 20,
                                "ask_size": 20,
                            }
                        },
                    },
                    "invalidate_symbols": [],
                }
            )
        return {
            "schema": SCHEMA,
            "origin": "SYNTHETIC_ENGINEERING_ONLY",
            "mode": "REPLAY",
            "initial_cash_usd": 1000,
            "initial_positions": [],
            "assets": {"SYNTHSVR": asset},
            "models": {
                "RIDGE": [copy.deepcopy(self.ridge)],
                "SVR": [copy.deepcopy(self.svr)],
            },
            "config": {
                "scenarios": 64,
                "gross_fraction": 1,
                "asset_fraction": 1,
                "factor_fraction": 1,
                "cvar_fraction": 0.2,
                "stress_fraction": 0.5,
                "daily_loss_fraction": 0.5,
                "drawdown_fraction": 0.5,
                "min_edge_usd": 0,
            },
            "policy": {
                "holding_hours": 24,
                "entry_cutoff_minutes": 10,
                "policy_id": "SYNTHETIC_ENGINEERING_POLICY",
                "policy_parity_verified": False,
            },
            "costs": {
                "per_share_usd": 0.5,
                "per_order_usd": 1,
                "slippage_bps": 0,
                "verified": False,
                "reference": "EXPLICIT_SYNTHETIC_TEST_COSTS",
            },
            "provenance": {
                "price_origin": "SYNTHETIC_ENGINEERING_ONLY",
                "execution_origin": "MODELED",
                "availability": "OBSERVED_TIMESTAMPS",
                "universe": "PREDEFINED_FIXED",
            },
            "frames": frames,
        }

    def force_two(self):
        return patch(
            "harpoon_quant.paired_replay.allocate",
            return_value={
                "selected": [
                    {"id": "PLUGIN|SYNTHSVR", "symbol": "SYNTHSVR", "quantity": 2}
                ],
                "execution_allowed": False,
                "expected_net_usd": 1_000_000,
            },
        )

    def test_round_trip_cash_fees_and_realized_profit_are_independently_reconciled(
        self,
    ):
        data = self.data()
        data["frames"] = data["frames"][:2]
        data["frames"][1]["invalidate_symbols"] = ["SYNTHSVR"]
        data["frames"][1]["execution"]["quotes"]["SYNTHSVR"].update(bid=105, ask=106)
        with self.force_two():
            result = run_paired_replay(data)
        r = result["policies"]["SVR"]
        # Buy 2*101 + 2 fees; sell 2*105 - 2 fees: net +4, not model +1e6.
        self.assertEqual(r["net_pnl_usd"], 4)
        self.assertEqual(r["realized_net_pnl_usd"], 4)
        self.assertEqual(r["execution_fees_usd"], 4)
        self.assertEqual(r["final_equity_usd"], 1004)
        self.assertEqual(r["open_positions"], {})
        self.assertEqual(sum(e.get("cash_change_usd", 0) for e in r["events"]), 4)
        self.assertFalse(result["financial_acceptance_allowed"])

    def test_external_costs_reduce_equity_and_are_not_neutralized_as_capital(self):
        data = self.data()
        for frame in data["frames"]:
            frame["opportunities"] = []
            frame["operating_costs_usd"] = {name: 2 for name in ("C0", "RIDGE", "SVR")}
        result = run_paired_replay(data)
        for r in result["policies"].values():
            self.assertEqual(r["final_equity_usd"], 994)
            self.assertEqual(r["net_pnl_usd"], -6)
            self.assertEqual(r["external_net_flows_usd"], 0)
            self.assertEqual(r["operating_costs_usd"], 6)

    def test_deposit_and_withdrawal_do_not_create_return(self):
        data = self.data()
        for frame in data["frames"]:
            frame["opportunities"] = []
        data["frames"][0]["external_flow_before_usd"] = 500
        data["frames"][1]["external_flow_before_usd"] = -200
        result = run_paired_replay(data)
        for r in result["policies"].values():
            self.assertEqual(r["net_pnl_usd"], 0)
            self.assertEqual(r["final_equity_usd"], 1300)
            self.assertEqual(r["growth_log_per_session"], 0)

    def test_deposit_does_not_dilute_price_gain_before_the_cash_flow(self):
        data = self.data()
        data["initial_cash_usd"] = 100
        data["initial_positions"] = [
            {
                "symbol": "SYNTHSVR",
                "quantity": 9,
                "entry_price": 100,
                "basis_per_share": 100,
                "entry_at": "2026-10-15T13:40:00+00:00",
            }
        ]
        data["frames"] = data["frames"][:2]
        for frame in data["frames"]:
            frame["opportunities"] = []
            frame["quotes"]["SYNTHSVR"].update(bid=100, ask=100)
            frame["execution"]["quotes"]["SYNTHSVR"].update(bid=100, ask=100)
        data["frames"][1]["quotes"]["SYNTHSVR"].update(bid=110, ask=110)
        data["frames"][1]["execution"]["quotes"]["SYNTHSVR"].update(bid=110, ask=110)
        data["frames"][1]["external_flow_before_usd"] = 1000
        result = run_paired_replay(data)
        for r in result["policies"].values():
            self.assertEqual(r["net_pnl_usd"], 90)
            self.assertEqual(r["final_equity_usd"], 2090)
            self.assertAlmostEqual(r["growth_log_per_session"], math.log(1.09))
            self.assertEqual(r["curve"][1]["pre_flow_equity_usd"], 1090)

    def test_open_losing_position_is_marked_and_not_closed_at_terminal(self):
        data = self.data()
        data["frames"] = data["frames"][:2]
        data["frames"][1]["quotes"]["SYNTHSVR"].update(bid=80, ask=81)
        data["frames"][1]["execution"]["quotes"]["SYNTHSVR"].update(bid=80, ask=81)
        with self.force_two():
            result = run_paired_replay(data)
        r = result["policies"]["RIDGE"]
        self.assertEqual(r["net_pnl_usd"], -44)
        self.assertEqual(r["realized_net_pnl_usd"], 0)
        self.assertEqual(r["open_positions"]["SYNTHSVR"]["quantity"], 2)
        self.assertEqual(sum(e["kind"] == "FILL" for e in r["events"]), 1)

    def test_partial_entry_and_unfilled_exit_preserve_inventory(self):
        data = self.data()
        data["frames"] = data["frames"][:2]
        data["frames"][0]["execution"]["quotes"]["SYNTHSVR"]["ask_size"] = 1
        data["frames"][1]["invalidate_symbols"] = ["SYNTHSVR"]
        data["frames"][1]["execution"]["quotes"]["SYNTHSVR"]["bid_size"] = 0
        with self.force_two():
            result = run_paired_replay(data)
        r = result["policies"]["RIDGE"]
        self.assertEqual(r["open_positions"]["SYNTHSVR"]["quantity"], 1)
        self.assertEqual(r["filled_quantity"], 1)
        self.assertEqual(r["requested_quantity"], 3)
        self.assertEqual(r["fill_ratio"], 1 / 3)

    def test_price_jump_cannot_overdraw_cash_or_expand_asset_limit(self):
        data = self.data()
        data["frames"] = data["frames"][:1]
        data["config"]["asset_fraction"] = 0.2
        data["frames"][0]["execution"]["quotes"]["SYNTHSVR"].update(bid=999, ask=1000)
        with self.force_two():
            result = run_paired_replay(data)
        r = result["policies"]["SVR"]
        self.assertEqual(r["fill_count"], 0)
        self.assertEqual(r["final_equity_usd"], 1000)

    def test_more_than_one_decision_per_session_preserves_every_record(self):
        data = self.data()
        with self.force_two():
            result = run_paired_replay(data)
        for r in result["policies"].values():
            self.assertEqual(
                [d["decision_id"] for d in r["decisions"]], ["D0", "D1", "D2"]
            )
            self.assertEqual(len(r["daily_returns"]), 1)
            self.assertEqual(
                [d["window"] for d in r["decisions"]],
                ["OPENING_90", "OPENING_90", "PRECLOSE_90"],
            )
        self.assertEqual(len(result["paired_comparison"]["session_ids"]), 1)

    def test_universe_is_identical_before_predictor_not_common_accepted_intersection(
        self,
    ):
        data = self.data()
        data["models"]["RIDGE"][0]["models"]["SYNTHSVR"]["accepted"] = False
        result = run_paired_replay(data)
        ridge = result["policies"]["RIDGE"]["decisions"][0]
        svr = result["policies"]["SVR"]["decisions"][0]
        self.assertEqual(ridge["universe_hash"], svr["universe_hash"])
        self.assertEqual(ridge["opportunity_count"], 1)
        self.assertEqual(ridge["plan"]["selected"], [])
        self.assertFalse(result["execution_allowed"])

    def test_actual_allocator_integration_preserves_shadow_permission(self):
        data = self.data()
        data["costs"].update(per_share_usd=0, per_order_usd=0)
        data["frames"] = data["frames"][:1]
        result = run_paired_replay(data)
        self.assertEqual(result["status"], "ENGINEERING_ONLY", result)
        for name in ("RIDGE", "SVR"):
            self.assertGreater(
                result["policies"][name]["fill_count"],
                0,
                result["policies"][name]["decisions"],
            )
        plan = result["policies"]["SVR"]["decisions"][0]["plan"]
        self.assertFalse(plan["execution_allowed"])
        self.assertEqual(plan["forecast_model_kind"], "SVR_RBF")
        self.assertFalse(result["policy_parity_verified"])

    def test_future_model_is_unavailable_even_when_supplied_in_history(self):
        data = self.data()
        for models in data["models"].values():
            models[0]["available_at"] = "2026-10-16T00:00:00+00:00"
        result = run_paired_replay(data)
        for name in ("RIDGE", "SVR"):
            r = result["policies"][name]
            self.assertEqual(r["fill_count"], 0)
            self.assertEqual(
                r["decisions"][0]["plan"]["reason"], "NO_MODEL_AVAILABLE_AT_DECISION"
            )

    def test_future_feature_and_same_time_fill_are_blocked_before_execution(self):
        for fault in ("feature", "execution"):
            data = self.data()
            if fault == "feature":
                data["frames"][0]["opportunities"][0]["features_known_at"] = (
                    "2026-10-16T00:00:00+00:00"
                )
            else:
                data["frames"][0]["execution"]["at"] = data["frames"][0]["at"]
            with self.subTest(fault=fault):
                result = run_paired_replay(data)
                self.assertEqual(result["status"], "MEDICION_BLOQUEADA")
                self.assertIsNone(result["policies"])

    def test_unknown_cost_is_null_result_not_zero(self):
        data = self.data()
        data["costs"]["per_share_usd"] = None
        result = run_paired_replay(data)
        self.assertFalse(result["readiness"]["computable"])
        self.assertIsNone(result["paired_comparison"])
        self.assertIsNone(result["policies"])

    def test_unknown_terminal_mark_does_not_erase_open_loss(self):
        data = self.data()
        data["frames"][1]["execution"]["quotes"] = {}
        with self.force_two():
            result = run_paired_replay(data)
        self.assertEqual(result["status"], "MEDICION_BLOQUEADA")
        self.assertIn("UNPRICED_OPEN_POSITION", result["reason"])
        self.assertIsNone(result["policies"])
        self.assertIn("partial_traces", result)

    def test_duplicate_decision_and_calibration_attempt_to_claim_parity_block(self):
        for fault in ("id", "parity"):
            data = self.data()
            if fault == "id":
                data["frames"][1]["decision_id"] = "D0"
            else:
                data["policy"]["policy_parity_verified"] = True
            with self.subTest(fault=fault):
                self.assertFalse(readiness(data)["computable"])

    def test_insolvency_is_preserved_and_injection_does_not_reset_risk(self):
        data = self.data()
        for frame in data["frames"]:
            frame["opportunities"] = []
        data["frames"][0]["operating_costs_usd"] = {
            name: 2000 for name in ("C0", "RIDGE", "SVR")
        }
        data["frames"][1]["external_flow_before_usd"] = 3000
        result = run_paired_replay(data)
        for r in result["policies"].values():
            self.assertEqual(r["curve"][0]["equity_usd"], -1000)
            self.assertTrue(r["insolvent"])
            self.assertIsNone(r["growth_log_per_session"])
            self.assertEqual(r["net_pnl_usd"], -2000)
            self.assertEqual(r["fill_count"], 0)

    def test_close_cutoff_prevents_new_entries_and_does_not_fake_exit(self):
        data = self.data()
        frame = data["frames"][0]
        frame["at"] = "2026-10-15T19:50:00+00:00"
        frame["execution"]["at"] = "2026-10-15T19:50:01+00:00"
        for quote in frame["quotes"].values():
            quote.update(at=frame["at"], known_at=frame["at"])
        for quote in frame["execution"]["quotes"].values():
            quote.update(at=frame["execution"]["at"], known_at=frame["execution"]["at"])
        data["frames"] = [frame]
        with self.force_two():
            result = run_paired_replay(data)
        for r in result["policies"].values():
            self.assertEqual(r["fill_count"], 0)
            self.assertEqual(
                r["decisions"][0]["plan"]["reason"], "OUTSIDE_ENTRY_SESSION"
            )

    def test_execution_outcome_is_not_visible_to_real_allocator_request(self):
        data = self.data()
        data["frames"] = data["frames"][:1]
        requests = []

        def inspect(request, model, cfg):
            requests.append(copy.deepcopy(request))
            return {"selected": [], "execution_allowed": False}

        with patch("harpoon_quant.paired_replay.allocate", side_effect=inspect):
            run_paired_replay(data)
        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertNotIn("execution", request)
            self.assertEqual(request["candidates"][0]["ask"], 101)
            self.assertEqual(request["asof"], data["frames"][0]["at"])

    def test_eight_sessions_with_many_assets_do_not_pass_training_gate(self):
        panel = copy.deepcopy(self.fixture["data"])
        panel["rows"] = [
            {**copy.deepcopy(row), "underlying": f"MOCK{asset}"}
            for row in self.fixture["data"]["rows"][:8]
            for asset in range(14)
        ]
        result = calibration_readiness(panel, self.fixture["available_at"], Config())
        self.assertEqual(result["distinct_sessions"], 8)
        self.assertEqual(result["observed_rows"], 112)
        self.assertEqual(result["reason"], "SVR_100_DISTINCT_SESSIONS_REQUIRED")
        self.assertFalse(result["training_executed"])

    def test_intraday_training_change_requires_versioned_residual_contract(self):
        panel = copy.deepcopy(self.fixture["data"])
        panel["observation_unit"] = "decision"
        result = calibration_readiness(panel, self.fixture["available_at"], Config())
        self.assertEqual(
            result["reason"],
            "SVR_DECISION_LEVEL_CALIBRATION_REQUIRES_RESIDUAL_CONTRACT",
        )
        panel.pop("observation_unit")
        panel["rows"].append(copy.deepcopy(panel["rows"][0]))
        self.assertEqual(
            calibration_readiness(panel, self.fixture["available_at"], Config())[
                "reason"
            ],
            "SVR_DUPLICATE_ASSET_SESSION",
        )

    def test_config_horizon_remains_twenty_four_hours_for_window_diagnostics(self):
        data = self.data()
        self.assertNotIn("horizon_hours", data["config"])
        result = run_paired_replay(data)
        self.assertEqual(self.svr["horizon_hours"], 24)
        self.assertEqual(
            result["config_hash"],
            digest({**Config(**data["config"]).__dict__, "slippage_bps": 0.0}),
        )

    def test_non_object_payload_fails_closed(self):
        for payload in (None, [], "not an object"):
            with self.subTest(payload=payload):
                result = run_paired_replay(payload)
                self.assertFalse(result["execution_allowed"])
                self.assertEqual(
                    result["readiness"]["blockers"], ["REPLAY_OBJECT_REQUIRED"]
                )

    def test_model_horizons_must_match_before_comparison(self):
        data = self.data()
        data["config"]["horizon_hours"] = 1.5
        result = run_paired_replay(data)
        self.assertEqual(result["status"], "MEDICION_BLOQUEADA")
        self.assertIn("REPLAY_MODEL_HORIZON_MISMATCH", result["readiness"]["blockers"])

    def test_invalid_numeric_cost_and_unknown_provenance_fail_closed(self):
        for fault in ("nan_cost", "unknown_provenance", "missing_models"):
            data = self.data()
            if fault == "nan_cost":
                data["costs"]["slippage_bps"] = float("nan")
            elif fault == "unknown_provenance":
                data["provenance"] = None
            else:
                data["models"] = None
            with self.subTest(fault=fault):
                self.assertEqual(
                    run_paired_replay(data)["status"], "MEDICION_BLOQUEADA"
                )

    def test_report_is_json_serializable_and_readiness_does_not_fit(self):
        data = self.data()
        with patch(
            "harpoon_quant.scalar_svr._fit", side_effect=AssertionError("NO_TRAINING")
        ):
            self.assertTrue(readiness(data)["computable"])
            result = run_paired_replay(data)
        text = json.dumps(result, allow_nan=False)
        self.assertEqual(json.loads(text)["execution_allowed"], False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.json"
            path.write_text(text)
            self.assertGreater(path.stat().st_size, 0)

    def test_ledger_detects_fee_cash_and_inventory_tampering(self):
        data = self.data()
        data["frames"] = data["frames"][:1]
        with self.force_two():
            result = run_paired_replay(data)
        report = result["policies"]["SVR"]
        self.assertEqual(report["accounting"]["status"], "INTERNALLY_RECONCILED")
        for fault in ("fee", "cash", "inventory"):
            changed = copy.deepcopy(report)
            if fault == "fee":
                next(e for e in changed["events"] if e["kind"] == "FILL")[
                    "fees_usd"
                ] += 1
            elif fault == "cash":
                changed["curve"][0]["cash_usd"] += 1
            else:
                changed["curve"][0]["positions"][0]["quantity"] += 1
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                reconcile_replay(changed, 1000, [])

    def test_slippage_prices_use_adverse_tick_and_are_not_debited_twice(self):
        data = self.data()
        data["frames"] = data["frames"][:1]
        data["costs"].update(slippage_bps=10, per_share_usd=0, per_order_usd=0)
        with self.force_two():
            result = run_paired_replay(data)
        r = result["policies"]["RIDGE"]
        fill = next(e for e in r["events"] if e["kind"] == "FILL")
        self.assertEqual(fill["price"], 101.11)
        self.assertAlmostEqual(r["net_pnl_usd"], -2.22)
        self.assertEqual(r["execution_fees_usd"], 0)

    def test_compute_budget_returns_partial_evidence_without_profit_metrics(self):
        data = self.data()
        data["policy"]["compute_budget_seconds"] = 1
        with patch("harpoon_quant.paired_replay.time.perf_counter", side_effect=[0, 2]):
            result = run_paired_replay(data)
        self.assertEqual(result["status"], "MEDICION_BLOQUEADA")
        self.assertEqual(result["reason"], "REPLAY_COMPUTE_BUDGET_EXCEEDED")
        self.assertIsNone(result["policies"])

    def test_close_timestamp_does_not_assume_access_to_closing_auction(self):
        data = self.data()
        data["frames"] = data["frames"][:1]
        frame = data["frames"][0]
        frame["execution"]["at"] = frame["close"]
        for q in frame["execution"]["quotes"].values():
            q.update(at=frame["close"], known_at=frame["close"])
        with self.force_two():
            result = run_paired_replay(data)
        r = result["policies"]["SVR"]
        self.assertEqual(r["fill_count"], 0)
        self.assertEqual(r["incidents"][0]["kind"], "EXECUTION_OUTSIDE_REGULAR_SESSION")

    def test_insolvency_at_decision_is_not_erased_by_later_price_recovery(self):
        data = self.data()
        data["initial_cash_usd"] = 100
        data["initial_positions"] = [
            {
                "symbol": "SYNTHSVR",
                "quantity": 2,
                "entry_price": 100,
                "basis_per_share": 100,
                "entry_at": "2026-10-15T13:40:00+00:00",
            }
        ]
        data["frames"] = data["frames"][:1]
        data["frames"][0]["operating_costs_usd"] = {
            name: 400 for name in ("C0", "RIDGE", "SVR")
        }
        data["frames"][0]["execution"]["quotes"]["SYNTHSVR"].update(bid=200, ask=201)
        result = run_paired_replay(data)
        for r in result["policies"].values():
            self.assertGreater(r["final_equity_usd"], 0)
            self.assertTrue(r["insolvent"])
            self.assertIsNone(r["growth_log_per_session"])
            self.assertEqual(r["incidents"][0]["equity_usd"], -100)

    def test_leveraged_exposure_requires_an_adapter_before_replay(self):
        for leverage in (0.5, 2, 3):
            data = self.data()
            data["assets"]["SYNTHSVR"].update(book="etf", leverage=leverage)
            data["config"]["factor_fraction"] = 0.3
            data["costs"].update(per_share_usd=0, per_order_usd=0)
            with self.subTest(leverage=leverage):
                with patch("harpoon_quant.paired_replay.allocate") as allocator:
                    result = run_paired_replay(data)
                allocator.assert_not_called()
                self.assertEqual(result["status"], "MEDICION_BLOQUEADA")
                self.assertEqual(
                    result["readiness"]["blockers"],
                    ["REPLAY_LEVERAGED_EXPOSURE_ADAPTER_REQUIRED"],
                )
                self.assertIsNone(result["policies"])

    def test_unleveraged_etf_remains_supported_without_scaling_its_price_return(self):
        data = self.data()
        data["assets"]["SYNTHSVR"]["book"] = "etf"
        data["frames"] = data["frames"][:1]
        data["config"]["factor_fraction"] = 0.3
        data["costs"].update(per_share_usd=0, per_order_usd=0)
        with self.force_two():
            result = run_paired_replay(data)
        for name in ("RIDGE", "SVR"):
            report = result["policies"][name]
            self.assertEqual(report["filled_quantity"], 2)
            self.assertEqual(report["net_pnl_usd"], -2)
            self.assertEqual(report["final_equity_usd"], 998)

    def test_svr_hidden_inside_relabelled_ridge_cannot_be_the_control(self):
        data = self.data()
        disguised = copy.deepcopy(data["models"]["SVR"][0])
        disguised["schema"] = "HARPOON_QUANT_CALIBRATION_1"
        disguised.pop("model_kind")
        disguised.pop("artifact_hash", None)
        disguised["artifact_hash"] = digest(disguised)
        data["models"]["RIDGE"] = [disguised]
        with patch("harpoon_quant.paired_replay.allocate") as allocator:
            result = run_paired_replay(data)
        allocator.assert_not_called()
        self.assertEqual(result["readiness"]["blockers"], ["REPLAY_ESTIMATOR_BINDING"])
        self.assertIsNone(result["paired_comparison"])

    def test_estimator_binding_checks_header_and_every_internal_family(self):
        for name in ("RIDGE", "SVR"):
            for fault in ("schema", "header_kind", "inner_kind", "inner_schema"):
                data = self.data()
                model = data["models"][name][0]
                if fault == "schema":
                    model["schema"] = "UNKNOWN_SCHEMA"
                elif fault == "header_kind":
                    model["model_kind"] = "UNKNOWN_ESTIMATOR"
                elif fault == "inner_kind":
                    model["models"]["SYNTHSVR"]["model_kind"] = (
                        "SVR_RBF" if name == "RIDGE" else "RIDGE"
                    )
                else:
                    model["models"]["OTHER"] = []
                with self.subTest(name=name, fault=fault):
                    result = readiness(data)
                    self.assertFalse(result["computable"])
                    self.assertEqual(result["blockers"], ["REPLAY_ESTIMATOR_BINDING"])

    def test_equivalent_model_timestamps_cannot_create_order_dependent_versions(self):
        for name in ("RIDGE", "SVR"):
            data = self.data()
            model = data["models"][name][0]
            duplicate = copy.deepcopy(model)
            duplicate["available_at"] = (
                timestamp(model["available_at"]).isoformat().replace("+00:00", "Z")
            )
            self.assertNotEqual(model["available_at"], duplicate["available_at"])
            data["models"][name].append(duplicate)
            with self.subTest(name=name):
                result = readiness(data)
                self.assertFalse(result["computable"])
                self.assertEqual(result["blockers"], ["REPLAY_AMBIGUOUS_MODEL_VERSION"])

    def held_data(self):
        data = self.data()
        data["initial_cash_usd"] = 100
        data["initial_positions"] = [
            {
                "symbol": "SYNTHSVR",
                "quantity": 9,
                "entry_price": 100,
                "basis_per_share": 100,
                "entry_at": "2026-10-15T13:40:00+00:00",
            }
        ]
        data["frames"] = data["frames"][:1]
        data["frames"][0]["opportunities"] = []
        return data

    def test_unfunded_withdrawal_preserves_cash_and_blocks_implicit_borrowing(self):
        data = self.held_data()
        data["frames"][0]["external_flow_before_usd"] = -200
        result = run_paired_replay(data)
        self.assertEqual(result["status"], "MEDICION_BLOQUEADA")
        self.assertEqual(result["reason"], "REPLAY_UNMODELED_FINANCING_DEFICIT")
        self.assertIsNone(result["policies"])
        trace = result["partial_traces"]["C0"]
        self.assertEqual(trace["cash_usd"], -100)
        self.assertEqual(trace["external_net_flows_usd"], -200)
        self.assertEqual(trace["positions"]["SYNTHSVR"]["quantity"], 9)
        self.assertEqual(trace["incidents"][0]["equity_usd"], 800)
        self.assertFalse(trace["insolvent"])
        self.assertEqual([e["kind"] for e in trace["events"]], ["CASH_FLOW_AND_COST"])

    def test_unfunded_operating_cost_remains_an_expense_in_the_blocked_trace(self):
        data = self.held_data()
        data["frames"][0]["operating_costs_usd"] = {
            name: 200 for name in ("C0", "RIDGE", "SVR")
        }
        result = run_paired_replay(data)
        self.assertEqual(result["reason"], "REPLAY_UNMODELED_FINANCING_DEFICIT")
        trace = result["partial_traces"]["C0"]
        self.assertEqual(trace["cash_usd"], -100)
        self.assertEqual(trace["operating_costs_usd"], 200)
        self.assertEqual(trace["external_net_flows_usd"], 0)
        self.assertEqual(trace["events"][0]["operating_cost_usd"], 200)
        self.assertEqual(trace["incidents"][0]["equity_usd"], 800)
        self.assertFalse(trace["insolvent"])

    def test_exit_fee_deficit_preserves_partial_fill_and_blocks_margin_assumption(self):
        data = self.held_data()
        data["costs"].update(per_order_usd=201, per_share_usd=0)
        data["frames"][0]["invalidate_symbols"] = ["SYNTHSVR"]
        data["frames"][0]["execution"]["quotes"]["SYNTHSVR"]["bid_size"] = 1
        result = run_paired_replay(data)
        self.assertEqual(result["reason"], "REPLAY_UNMODELED_FINANCING_DEFICIT")
        trace = result["partial_traces"]["C0"]
        self.assertEqual(trace["cash_usd"], -1)
        self.assertEqual(trace["positions"]["SYNTHSVR"]["quantity"], 8)
        fill = next(event for event in trace["events"] if event["kind"] == "FILL")
        self.assertEqual(fill["quantity"], 1)
        self.assertEqual(fill["fees_usd"], 201)
        self.assertEqual(trace["incidents"][0]["equity_usd"], 799)
        self.assertEqual(trace["incidents"][0]["stage"], "AFTER_EXECUTION")


if __name__ == "__main__":
    unittest.main()
