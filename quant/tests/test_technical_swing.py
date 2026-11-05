from __future__ import annotations

import copy
import unittest

from harpoon_quant.calibration import fit
from harpoon_quant.core import FEATURES, Config, allocate, digest
from harpoon_quant.feature_policy import named_subset, path_fields, regime_fields
from harpoon_quant.frontier.contracts import Settings
from harpoon_quant.frontier.paths import fit as path_fit
from harpoon_quant.frontier.paths import predict as path_predict
from harpoon_quant.frontier_core import shadow
from harpoon_quant.microstructure import FEATURE_NAMES
from harpoon_quant.technical_swing import BAR, TechnicalSwing
from test_frontier_core import fixture
from test_quant import calibration, candidate, request
from test_scalar_svr import FIXTURE


def market() -> dict:
    sessions = [
        {"open": 86_400_000 * d, "close": 86_400_000 * d + BAR * 78} for d in range(22)
    ]
    series = []
    for symbol in ("A", "B", "SECTOR"):
        bars = []
        for d, s in enumerate(sessions):
            for i in range(12):
                t = s["open"] + i * BAR
                confirm = symbol != "SECTOR" and d == 20 and i >= 10
                c = 102 if confirm else 100
                bars.append(
                    {
                        "t": t,
                        "end": t + BAR,
                        "availableAt": t + BAR + 1000,
                        "o": 100,
                        "c": c,
                        "h": c + 1,
                        "l": 99,
                        "v": 200 if confirm else 100,
                    }
                )
        series.append({"symbol": symbol, "bars": bars})
    return {"schema": "HARPOON-ULTIMATE-DATA-1", "sessions": sessions, "series": series}


class SwingTests(unittest.TestCase):
    def setUp(self):
        self.data = market()
        self.at = self.data["sessions"][20]["open"] + 12 * BAR + 1000

    def score(self):
        return TechnicalSwing(self.data, ["B", "A"], "SECTOR").decision(self.at)

    def test_confirmation_and_stable_tie(self):
        result = self.score()
        self.assertEqual(result["confirmed"]["symbol"], "A")
        self.assertEqual(result["confirmed"]["rvol"], 2)
        self.assertEqual(result["confirmed"]["stop_distance"], 3)
        self.assertEqual(result["planned_entry_at"] - self.at, BAR - 1000)
        self.assertFalse(result["execution_allowed"])

    def test_simple_and_cash_when_no_confirmation(self):
        for series in self.data["series"][:2]:
            series["bars"][20 * 12 + 10]["c"] = 100
        r = self.score()
        self.assertIsNone(r["confirmed"])
        self.assertEqual(r["simple"]["symbol"], "A")

    def test_future_bars_and_exogenous_information_are_inert(self):
        expected = self.score()
        self.data["guidance"] = 10**12
        self.data["dividendEvents"] = [{"rate": 1234}]
        for series in self.data["series"]:
            for b in series["bars"]:
                b["eps"] = -999
                if b["t"] > self.at:
                    b["c"] = b["h"] = 12345
        self.assertEqual(self.score(), expected)

    def test_missing_late_split_and_zero_volume_abstain(self):
        a, b = self.data["series"][:2]
        a["bars"][20 * 12 + 11]["availableAt"] = self.at + 1
        self.data["splitEvents"] = [{"symbol": "B", "at": self.at - 10 * BAR}]
        r = self.score()
        self.assertIsNone(r["simple"])
        self.assertEqual(set(r["refusals"]), {"A", "B"})
        self.data.pop("splitEvents")
        for bar in b["bars"]:
            if bar["end"] < self.data["sessions"][20]["open"]:
                bar["v"] = 0
        self.assertEqual(self.score()["refusals"]["B"], "NO_COMPARABLE_VOLUME")
        del a["bars"][20 * 12 + 11]
        self.assertEqual(
            self.score()["refusals"]["A"], "INCOMPLETE_OR_UNAVAILABLE_BARS"
        )

    def test_warmup_grid_and_duplicates(self):
        p = TechnicalSwing(self.data, ["A"], "SECTOR")
        first = self.data["sessions"][0]["open"] + 12 * BAR + 1000
        self.assertIsNone(p.decision(first)["confirmed"])
        with self.assertRaisesRegex(ValueError, "DECISION_MUST_BE"):
            p.decision(self.at - 1)
        self.data["series"][0]["bars"].append(self.data["series"][0]["bars"][-1])
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            TechnicalSwing(self.data, ["A"], "SECTOR")


class InputPolicyTests(unittest.TestCase):
    def test_renamed_columns_block_ridge_svr_and_allocation(self):
        f = FIXTURE.build_fixture()
        bad = [*FEATURES[:-1], "earnings_surprise"]
        for estimator in ("ridge", "svr"):
            with self.subTest(estimator=estimator):
                for row_level in (False, True):
                    data = copy.deepcopy(f["data"])
                    (data["rows"][0] if row_level else data)["feature_names"] = bad
                    with self.assertRaisesRegex(
                        ValueError, "FEATURE_ORDER|MODEL_SCHEMA"
                    ):
                        fit(
                            data,
                            f["available_at"],
                            Config(**f["config"]),
                            estimator=estimator,
                        )
        c = {**candidate(), "feature_names": bad}
        result = allocate(request([c]), calibration(), Config())
        self.assertFalse(result["selected"])
        self.assertIn("TECHNICAL_FEATURE_ORDER", result["rejected"][c["id"]])

    def test_imported_models_and_context_contracts(self):
        data, at, state = fixture()
        cfg = Settings()
        model = path_fit(data, at, cfg)
        bad = ["SYNTHETIC_VOL", "revenue_growth"]
        data["feature_names"] = bad
        with self.assertRaisesRegex(ValueError, "UNREGISTERED"):
            path_fit(data, at, cfg)
        model["feature_names"] = state["feature_names"] = bad
        model["model_hash"] = digest(
            {k: v for k, v in model.items() if k != "model_hash"}
        )
        with self.assertRaisesRegex(ValueError, "UNREGISTERED"):
            path_predict(model, state, cfg)
        for call in (
            lambda: named_subset(["guidance"], FEATURE_NAMES),
            lambda: regime_fields(["earnings"]),
            lambda: path_fields(["SYNTHETIC_VOL"], ["A"], "OBSERVED"),
        ):
            with self.assertRaisesRegex(ValueError, "UNREGISTERED"):
                call()

    def test_dividend_scenarios_cannot_buy_a_losing_tape(self):
        data, at, state = fixture(trend=-0.0005)
        cfg = Settings()
        for sample in data["samples"]:
            sample["dividend_cash"][0] = [0.25] * 72
        with_div = shadow(state, path_fit(data, at, cfg), cfg)
        del data["dividend_basis"]
        for sample in data["samples"]:
            del sample["dividend_cash"]
        only_prices = shadow(state, path_fit(data, at, cfg), cfg)
        self.assertEqual(with_div["supervisor"]["targets"], [0])
        self.assertEqual(with_div["supervisor"], only_prices["supervisor"])


if __name__ == "__main__":
    unittest.main()
