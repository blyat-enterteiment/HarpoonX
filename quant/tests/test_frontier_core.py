"""Synthetic engineering fixtures. Never market-performance or brokerage evidence."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harpoon_quant.core import digest
from harpoon_quant.frontier.assurance import assure
from harpoon_quant.frontier.contracts import Settings
from harpoon_quant.frontier.controller import decide, weighted_cvar, weighted_hac_se
from harpoon_quant.frontier.journal import Journal
from harpoon_quant.frontier.paths import competing_outcomes, fit
from harpoon_quant.frontier.supervisor import certify
from harpoon_quant.frontier_core import read_json, shadow, write_json


def fixture(n: int = 1, trend: float = 0.0005):
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD"][:n]
    rows = []
    start = datetime(2024, 1, 1, 12, tzinfo=UTC)
    for i in range(24):
        prices = []
        for _ in symbols:
            path = []
            for h in range(72):
                opening = 1 + h * trend
                closing = 1 + (h + 1) * trend
                path.append(
                    [
                        opening,
                        max(opening, closing) + 0.0001,
                        min(opening, closing) - 0.0001,
                        closing,
                    ]
                )
            prices.append(path)
        began = start + timedelta(days=i * 7)
        rows.append(
            {
                "id": f"SYNTHETIC-{i}",
                "start_at": began.isoformat(),
                "features_known_at": began.isoformat(),
                "label_end": (began + timedelta(hours=72)).isoformat(),
                "known_at": (began + timedelta(hours=72, minutes=1)).isoformat(),
                "features": [float(i % 5), float((i % 3) - 1)],
                "ohlc": prices,
                "dividend_cash": np.zeros((n, 72)).tolist(),
                "schedule": [[True] * 72 for _ in symbols],
                "source_hash": digest({"synthetic_original_case": i}),
            }
        )
    dataset = {
        "schema": "HARPOON_JOINT_PATH_DATASET_1",
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "symbols": symbols,
        "feature_names": ["SYNTHETIC_VOL", "SYNTHETIC_MOM"],
        "price_basis": "SPLIT_ADJUSTED_TO_SAMPLE_ENTRY_SHARE_UNIT",
        "dividend_basis": "FRACTION_OF_ENTRY_PRICE_PER_ENTRY_SHARE",
        "corporate_actions_covered": True,
        "samples": rows,
    }
    available = "2024-07-01T00:00:00+00:00"
    now = "2024-07-01T12:00:00+00:00"
    assets = []
    for s in symbols:
        assets.append(
            {
                "symbol": s,
                "book": "crypto",
                "factor": s,
                "bid": 99.99,
                "ask": 100.01,
                "quote_at": now,
                "quote_received_at": now,
                "status_known_at": now,
                "tradable_now": True,
                "halted": False,
                "quote_origin": "MODELED_FROM_BAR",
                "available_buy_qty": 100.0,
                "available_sell_qty": 100.0,
                "lot_qty": 1.0,
                "current_lots": 0,
                "max_new_lots": 10,
                "fee_bps": 0.0,
                "slippage_bps": 0.0,
                "fixed_order_fee_usd": 0.0,
                "cost_origin": "ASSUMED",
                "schedule": [True] * 72,
                "schedule_known_at": now,
                "schedule_source_hash": digest({"SYNTHETIC_CALENDAR": s}),
            }
        )
    state = {
        "schema": "HARPOON_FRONTIER_STATE_1",
        "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "asof": now,
        "known_at": now,
        "currency": "USD",
        "account_binding": "SYNTHETIC-TEST-ACCOUNT",
        "version": 1,
        "inventory_complete": True,
        "cash_usd": 20000.0,
        "pending_cash_usd": 0.0,
        "receivables_usd": 0.0,
        "daily_pnl_usd": 0.0,
        "drawdown_fraction": 0.0,
        "assets": assets,
        "features": [2.0, 0.0],
        "feature_names": dataset["feature_names"],
        "features_known_at": now,
        "evaluation_hours": 72,
    }
    return dataset, available, state


class FrontierTests(unittest.TestCase):
    def setUp(self):
        self.dataset, self.available, self.state = fixture()
        self.cfg = Settings()
        self.model = fit(self.dataset, self.available, self.cfg)

    def result(self, state=None, model=None):
        return decide(state or self.state, model or self.model, self.cfg)

    def held(self, lots=10, *, expired=False):
        state = copy.deepcopy(self.state)
        a = state["assets"][0]
        now = datetime.fromisoformat(state["asof"])
        a.update(
            campaign_id="SYNTHETIC-CAMPAIGN-1",
            current_lots=lots,
            max_new_lots=0,
            opened_at=(now - timedelta(hours=73 if expired else 24)).isoformat(),
            deadline=(
                now - timedelta(hours=1) if expired else now + timedelta(hours=48)
            ).isoformat(),
            stop_price=98.0,
            target_price=103.0,
        )
        return state

    def test_positive_path_can_enter_and_never_authorizes(self):
        r = self.result()
        self.assertEqual(r["status"], "SUPERVISED_RESEARCH_PROPOSAL", r)
        self.assertGreater(r["supervisor"]["targets"][0], 0)
        self.assertFalse(r["execution_allowed"])
        self.assertFalse(r["level9_accredited"])

    def test_losing_paths_abstain(self):
        data, at, state = fixture(trend=-0.0005)
        r = self.result(state, fit(data, at, self.cfg))
        self.assertEqual(r["supervisor"]["targets"], [0])

    def test_all_costs_can_destroy_edge(self):
        state = copy.deepcopy(self.state)
        state["assets"][0].update(fee_bps=200, fixed_order_fee_usd=10)
        self.assertEqual(self.result(state)["supervisor"]["targets"], [0])

    def test_calibration_before_label_maturity_rejected(self):
        self.dataset["samples"][-1]["known_at"] = "2024-08-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "UNMATURED"):
            fit(self.dataset, self.available, self.cfg)

    def test_future_training_features_rejected(self):
        self.dataset["samples"][0]["features_known_at"] = "2025-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "FUTURE_TRAINING"):
            fit(self.dataset, self.available, self.cfg)

    def test_bootstrap_replicates_not_new_original_cases(self):
        self.dataset["samples"][1]["start_at"] = self.dataset["samples"][0]["start_at"]
        with self.assertRaises(ValueError):
            fit(self.dataset, self.available, self.cfg)

    def test_future_query_feature_blocked(self):
        self.state["features_known_at"] = "2024-07-02T00:00:00Z"
        self.assertIn("FUTURE_QUERY", self.result()["reason"])

    def test_model_hash_tamper_blocked(self):
        self.model["location"][0] += 1
        self.assertIn("HASH_MISMATCH", self.result()["reason"])

    def test_synthetic_cannot_be_observed(self):
        self.state["origin"] = "OBSERVED"
        self.state["assets"][0]["quote_origin"] = "OBSERVED_BBO"
        self.assertIn("SYNTHETIC_MODEL", self.result()["reason"])

    def test_stale_or_future_quotes_blocked(self):
        for at in ("2024-07-01T11:59:00Z", "2024-07-01T12:00:01Z"):
            state = copy.deepcopy(self.state)
            state["assets"][0]["quote_at"] = at
            self.assertEqual(self.result(state)["status"], "BLOCKED")

    def test_calendar_support_is_not_fabricated(self):
        self.state["assets"][0]["schedule"][30] = False
        self.assertIn("CONDITIONAL_SUPPORT", self.result()["reason"])

    def test_regime_drift_abstains(self):
        self.state["features"] = [1000.0, 0.0]
        self.assertIn("DRIFT", self.result()["reason"])

    def test_hold_on_positive_paths(self):
        r = self.result(self.held())
        self.assertEqual(r["supervisor"]["actions"][0]["action"], "HOLD", r)

    def test_exit_on_losing_paths(self):
        data, at, _ = fixture(trend=-0.0005)
        r = self.result(self.held(), fit(data, at, self.cfg))
        self.assertEqual(r["supervisor"]["actions"][0]["action"], "EXIT", r)

    def test_expired_position_exit_and_no_deadline_reset(self):
        state = self.held(expired=True)
        r = self.result(state)
        self.assertEqual(r["supervisor"]["actions"][0]["action"], "EXIT", r)
        self.assertEqual(
            r["supervisor"]["actions"][0]["deadline"], state["assets"][0]["deadline"]
        )

    def test_expired_halted_position_not_fictionally_closed(self):
        state = self.held(expired=True)
        state["assets"][0]["halted"] = True
        self.assertEqual(self.result(state)["status"], "BLOCKED")

    def test_current_stop_trigger_exits(self):
        state = self.held()
        state["assets"][0]["stop_price"] = 100.0
        r = self.result(state)
        self.assertEqual(r["supervisor"]["actions"][0]["action"], "EXIT", r)

    def test_pending_cash_cannot_be_spent(self):
        self.state["pending_cash_usd"] = 19999.0
        self.assertEqual(self.result()["supervisor"]["targets"], [0])

    def test_unconfirmed_sale_does_not_fund_buy(self):
        _data, _at, state = fixture(2)
        state["cash_usd"] = 1.0
        now = datetime.fromisoformat(state["asof"])
        state["assets"][0].update(
            campaign_id="SYNTHETIC-CAMPAIGN-1",
            current_lots=10,
            opened_at=(now - timedelta(hours=1)).isoformat(),
            deadline=(now + timedelta(hours=48)).isoformat(),
            stop_price=98,
            target_price=103,
        )
        with self.assertRaisesRegex(ValueError, "FUNDING_RESERVE"):
            certify(state, [0, 10], self.cfg)

    def test_risk_pause_forbids_new_buys_not_exits(self):
        self.state["drawdown_fraction"] = 0.2
        self.assertEqual(self.result()["supervisor"]["targets"], [0])
        state = self.held()
        state["drawdown_fraction"] = 0.2
        self.assertNotEqual(self.result(state)["status"], "BLOCKED")

    def test_noninteger_qty_and_nonlinear_instrument_rejected(self):
        for key, value in [("current_lots", 0.5), ("book", "options")]:
            state = copy.deepcopy(self.state)
            state["assets"][0][key] = value
            self.assertEqual(self.result(state)["status"], "BLOCKED")

    def test_shared_overhead_same_for_cash_and_enter(self):
        r = self.result()
        # 10 lots: buy100.01, exit102.4 less modeled halfspread0.01%, minus3USD shared.
        self.assertAlmostEqual(r["scenarios"][0]["mean_net_change_usd"], 20.7976)
        state = copy.deepcopy(self.state)
        state["assets"][0]["max_new_lots"] = 0
        cash = self.result(state)
        self.assertAlmostEqual(cash["scenarios"][0]["mean_net_change_usd"], -3)
        self.assertAlmostEqual(cash["scenarios"][1]["mean_net_change_usd"], -6)

    def test_barrier_collision_partially_identified(self):
        p = np.ones((2, 72, 4))
        p[:, :, 1] = 1.01
        p[:, :, 2] = 0.99
        p[:, 0, 1] = 1.04
        p[:, 0, 2] = 0.96
        r = competing_outcomes(p, [0.5, 0.5], 0.98, 1.03, [True] * 72, 48)
        self.assertEqual(r["probabilities"]["ambiguous"], 1)
        self.assertEqual(r["target_probability_bounds"], [0, 1])

    def test_fractional_weighted_tail_mass(self):
        value = weighted_cvar(np.array([100.0, 0.0]), np.array([0.01, 0.99]))
        self.assertAlmostEqual(value, 20)

    def test_constant_weighted_hac_zero(self):
        self.assertEqual(weighted_hac_se(np.ones(20), np.ones(20) / 20, 5), 0)

    def test_grid_budget_blocks_without_partial_search(self):
        cfg = replace(self.cfg, max_grid=1)
        r = decide(self.state, self.model, cfg)
        self.assertIn("GRID_BUDGET", r["reason"])

    def test_journal_idempotent_and_stale_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private.sqlite"
            r = shadow(self.state, self.model, self.cfg, path)
            self.assertEqual(r, shadow(self.state, self.model, self.cfg, path))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            state = copy.deepcopy(self.state)
            state["cash_usd"] += 1
            with self.assertRaisesRegex(ValueError, "VERSION_REUSED"):
                shadow(state, self.model, self.cfg, path)
            journal = Journal(path)
            self.assertEqual(journal.verify()["rows"], 1)
            journal.close()

    def test_journal_tamper_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Journal(Path(tmp) / "r.sqlite")
            journal.append("SYNTHETIC", 2, "h", {"execution_allowed": False})
            journal.connection.execute("UPDATE receipts SET receipt='{}'")
            journal.connection.commit()
            with self.assertRaisesRegex(ValueError, "TAMPERED"):
                journal.verify()
            journal.close()

    def test_strict_json_duplicate_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "input.json"
            for data in ('{"x":1,"x":2}', '{"x":NaN}'):
                p.write_text(data)
                with self.assertRaises(ValueError):
                    read_json(p)

    def test_private_no_overwrite_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "out.json"
            write_json(p, {"test": "SYNTHETIC"})
            with self.assertRaises(FileExistsError):
                write_json(p, {})
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_incomplete_inventory_blocks(self):
        self.state["inventory_complete"] = False
        self.assertIn("COMPLETE_INVENTORY", self.result()["reason"])

    def test_quote_liquidity_not_invented(self):
        self.state["assets"][0]["available_buy_qty"] = 0
        self.assertEqual(self.result()["supervisor"]["targets"], [0])
        state = self.held(expired=True)
        state["assets"][0]["available_sell_qty"] = 1
        self.assertEqual(self.result(state)["status"], "BLOCKED")

    def test_fixed_overhead_can_destroy_total_edge(self):
        result = decide(
            self.state, self.model, replace(self.cfg, overhead_usd_per_day=50)
        )
        self.assertEqual(result["supervisor"]["targets"], [0])

    def test_existing_exposure_can_be_reduced(self):
        result = self.result(self.held(lots=100))
        self.assertEqual(result["supervisor"]["actions"][0]["action"], "REDUCE", result)
        self.assertTrue(result["supervisor"]["within_exposure_limits_after_full_fill"])

    def test_raw_dollar_paths_cannot_be_relative_returns(self):
        for row in self.dataset["samples"]:
            row["ohlc"] = (np.asarray(row["ohlc"]) * 100).tolist()
        with self.assertRaisesRegex(ValueError, "NORMALIZED_PRICE"):
            fit(self.dataset, self.available, self.cfg)

    def test_ambiguous_rollout_is_conservative_and_disclosed(self):
        data = copy.deepcopy(self.dataset)
        for row in data["samples"]:
            row["ohlc"][0][0][1] = 1.04
            row["ohlc"][0][0][2] = 0.96
        result = self.result(model=fit(data, self.available, self.cfg))
        self.assertEqual(result["supervisor"]["targets"], [0])

    def test_negative_probability_weights_rejected(self):
        with self.assertRaisesRegex(ValueError, "TAIL_DOMAIN"):
            weighted_cvar(np.array([1.0, 2.0]), np.array([-1.0, 2.0]))
        with self.assertRaisesRegex(ValueError, "HAC_DOMAIN"):
            weighted_hac_se(np.ones(20), np.ones(20), 5)

    def test_campaign_deadline_cannot_be_reset_between_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.sqlite"
            state = self.held()
            shadow(state, self.model, self.cfg, path)
            moved = copy.deepcopy(state)
            moved["version"] = 2
            for field in ("opened_at", "deadline"):
                moved["assets"][0][field] = (
                    datetime.fromisoformat(moved["assets"][0][field])
                    + timedelta(hours=1)
                ).isoformat()
            with self.assertRaisesRegex(ValueError, "DEADLINE_CHANGED"):
                shadow(moved, self.model, self.cfg, path)

    def test_unreconciled_campaign_replacement_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.sqlite"
            state = self.held()
            shadow(state, self.model, self.cfg, path)
            state["version"] = 2
            state["assets"][0]["campaign_id"] = "ANOTHER-SYNTHETIC-CAMPAIGN"
            with self.assertRaisesRegex(ValueError, "REPLACEMENT"):
                shadow(state, self.model, self.cfg, path)

    def test_campaign_index_tampering_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.sqlite"
            shadow(self.held(), self.model, self.cfg, path)
            journal = Journal(path)
            journal.connection.execute("UPDATE campaigns SET binding='{}'")
            journal.connection.commit()
            with self.assertRaisesRegex(ValueError, "INDEX_TAMPERED"):
                journal.verify()
            journal.close()

    def test_separate_decimal_repricing_matches(self):
        receipt = self.result()
        check = assure(self.state, self.model, receipt, self.cfg)
        self.assertTrue(check["verified"])
        self.assertFalse(check["independent_external_auditor"])

    def test_rehashed_numeric_tamper_rejected(self):
        receipt = self.result()
        receipt["scenarios"][0]["mean_net_change_usd"] += 1
        receipt["receipt_hash"] = digest(
            {k: v for k, v in receipt.items() if k != "receipt_hash"}
        )
        with self.assertRaisesRegex(ValueError, "REPRICING"):
            assure(self.state, self.model, receipt, self.cfg)

    def test_false_risk_reduction_exception_rejected(self):
        receipt = self.result()
        receipt["scenarios"][0]["risk_reduction_not_tail_certified"] = True
        receipt["receipt_hash"] = digest(
            {k: v for k, v in receipt.items() if k != "receipt_hash"}
        )
        with self.assertRaisesRegex(ValueError, "REDUCTION_EXCEPTION"):
            assure(self.state, self.model, receipt, self.cfg)

    def test_original_case_ids_tamper_rejected(self):
        receipt = self.result()
        receipt["case_ids"][0] = "NOT-AN-ORIGINAL-CASE"
        receipt["receipt_hash"] = digest(
            {k: v for k, v in receipt.items() if k != "receipt_hash"}
        )
        with self.assertRaisesRegex(ValueError, "CASE_IDS"):
            assure(self.state, self.model, receipt, self.cfg)

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            dataset, state = folder / "dataset.json", folder / "state.json"
            dataset.write_text(json.dumps(self.dataset))
            state.write_text(json.dumps(self.state))
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            for args in (
                [
                    "fit",
                    "--dataset",
                    str(dataset),
                    "--available-at",
                    self.available,
                    "--output",
                    str(folder / "model.json"),
                ],
                [
                    "decide",
                    "--model",
                    str(folder / "model.json"),
                    "--state",
                    str(state),
                    "--journal",
                    str(folder / "journal.sqlite"),
                    "--output",
                    str(folder / "decision.json"),
                ],
                [
                    "audit-journal",
                    "--journal",
                    str(folder / "journal.sqlite"),
                    "--output",
                    str(folder / "audit.json"),
                ],
            ):
                subprocess.run(
                    [sys.executable, "-B", "-m", "harpoon_quant.frontier_core", *args],
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            self.assertTrue(read_json(folder / "audit.json")["verified"])
            self.assertFalse(read_json(folder / "decision.json")["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
