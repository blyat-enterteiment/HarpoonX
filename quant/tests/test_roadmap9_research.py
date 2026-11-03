"""Engineering tests; fixtures are synthetic and never new market cases."""

from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build_roadmap9_replay
from audit_roadmap9_results import audit_report
from harpoon_quant.roadmap9.forecast import BAR, HOUR, ClockPanel, fit_ridge
from harpoon_quant.roadmap9.research import RECIPE_IDS


def rows_fixture():
    rows = []
    start = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
    for day in range(180):
        for stock in range(2):
            at = start + day * 24 * HOUR + 10 * HOUR
            x = [
                math.sin(day / 13),
                math.cos(day / 17),
                math.sin(day / 11),
                0.01 + 0.001 * math.cos(day / 8),
                0.01 * math.sin(day / 5),
                0.01 * math.cos(day / 7),
                0.15 + 0.1 * stock,
            ]
            y = 0.005 + 0.001 * x[0] - 0.0005 * x[1]
            rows.append(
                {
                    "session": f"{day:04d}",
                    "symbol": ("AAPL", "MSFT")[stock],
                    "decision_at": at,
                    "available_at": at,
                    "x": x,
                    "labels": {
                        str(h): {
                            "value": y,
                            "overnight": 0.3 * y,
                            "intraday": 0.7 * y,
                            "known_at": at + h * HOUR,
                            "exit_at": at + h * HOUR - BAR,
                        }
                        for h in (24, 48, 72)
                    },
                }
            )
    return rows


def tape_fixture():
    sessions, series = [], {s: [] for s in ("AAPL", "MSFT", "XLK")}
    start = int(datetime(2024, 1, 1, 14, 30, tzinfo=UTC).timestamp() * 1000)
    for day in range(40):
        opening = start + day * 24 * HOUR
        sessions.append(
            {
                "date": datetime.fromtimestamp(opening / 1000, UTC).date().isoformat(),
                "open": opening,
                "close": opening + 78 * BAR,
            }
        )
        for j in range(78):
            at = opening + j * BAR
            for k, symbol in enumerate(series):
                price = 100 + day * 0.1 + j * 0.01 + k
                series[symbol].append(
                    {
                        "t": at,
                        "end": at + BAR,
                        "availableAt": at + BAR + 1000,
                        "o": price,
                        "c": price + 0.005,
                        "h": price + 0.02,
                        "l": price - 0.02,
                        "v": 1000,
                        "vw": price,
                    }
                )
    return {
        "schema": "HARPOON-ULTIMATE-DATA-1",
        "sessions": sessions,
        "splitEvents": [],
        "series": [{"symbol": s, "bars": b} for s, b in series.items()],
    }


class CausalResearchTests(unittest.TestCase):
    def test_decomposition_and_future_prices_do_not_change_features(self):
        data = tape_fixture()
        at = data["sessions"][20]["open"] + HOUR + 1000
        expected = ClockPanel(data).features("AAPL", at)
        self.assertIsNotNone(expected)
        changed = copy.deepcopy(data)
        for series in changed["series"]:
            for b in series["bars"]:
                if b["availableAt"] > at:
                    for k in ("o", "h", "l", "c", "vw"):
                        b[k] *= 2
        self.assertEqual(expected, ClockPanel(changed).features("AAPL", at))
        self.assertLess(abs(expected["decomposition_residual"]), 1e-12)
        self.assertLessEqual(expected["available_at"], at)
        self.assertGreater(expected["planned_entry_at"], at)

    def test_label_components_and_maturity(self):
        panel = ClockPanel(tape_fixture())
        rows = panel.rows()
        self.assertTrue(rows)
        for row in rows:
            for label in row["labels"].values():
                self.assertAlmostEqual(
                    label["value"], label["overnight"] + label["intraday"], places=13
                )
                self.assertGreater(label["known_at"], label["exit_at"])
                self.assertLessEqual(label["exit_at"] - row["decision_at"], 72 * HOUR)

    def test_split_in_full_lookback_blocks_without_inventing_known_at(self):
        data = tape_fixture()
        at = data["sessions"][22]["open"] + HOUR + 1000
        data["splitEvents"] = [
            {"symbol": "AAPL", "at": data["sessions"][19]["open"], "ratio": 2}
        ]
        panel = ClockPanel(data)
        self.assertIsNone(panel.features("AAPL", at))
        self.assertIsNotNone(panel.features("MSFT", at))
        earlier = next(
            r
            for r in panel.rows()
            if r["symbol"] == "AAPL" and r["session_index"] == 18
        )
        self.assertNotIn("72", earlier["labels"])

    def test_ridge_purges_future_labels_and_training_calibration(self):
        rows = rows_fixture()
        at = rows[300]["decision_at"]
        model = fit_ridge(rows, at, 24)
        changed = copy.deepcopy(rows)
        for row in changed:
            if row["labels"]["24"]["known_at"] > at:
                row["labels"]["24"].update(value=999, overnight=-999, intraday=1998)
        actual = fit_ridge(changed, at, 24)
        self.assertEqual(model.to_dict(), actual.to_dict())
        self.assertLessEqual(model.latest_label_at, at)
        self.assertLessEqual(model.calibration["maximum_label_known_at"], at)
        self.assertEqual(model.calibration["calibration_sessions"], 20)
        self.assertGreaterEqual(model.calibration["train_sessions"], 60)
        pred = model.predict(rows[300])
        self.assertAlmostEqual(
            pred["mean"], pred["overnight_mean"] + pred["intraday_mean"], places=12
        )

    def test_stale_labels_cannot_be_hidden_by_new_fit_timestamp(self):
        rows = rows_fixture()
        at = rows[300]["decision_at"]
        model = fit_ridge(rows, at, 24)
        stale = replace(model, latest_label_at=at - 169 * HOUR)
        with self.assertRaisesRegex(ValueError, "STALE_LABELS"):
            stale.predict(rows[300])
        with self.assertRaisesRegex(ValueError, "CALIBRATION_REFERENCE_FAILURE"):
            replace(model, calibration={"pass": False}).predict(rows[300])
        future = copy.deepcopy(rows[300])
        future["available_at"] = at + 1
        with self.assertRaisesRegex(ValueError, "FUTURE_FEATURE"):
            model.predict(future)
        drift = copy.deepcopy(rows[300])
        drift["x"][0] = 1000
        with self.assertRaisesRegex(ValueError, "FEATURE_DRIFT"):
            model.predict(drift)

    def test_calendar_deadline_uses_received_sessions_and_original_clock(self):
        data = tape_fixture()
        panel = ClockPanel(data)
        friday = int(datetime(2025, 1, 3, 14, 30, tzinfo=UTC).timestamp() * 1000)
        monday = friday + 72 * HOUR
        panel.sessions = [
            {"open": friday, "close": friday + 6 * HOUR},
            {"open": monday, "close": monday + 6 * HOUR},
        ]
        decision = friday + HOUR + 1000
        self.assertEqual(panel.deadline(decision, 24), friday + 6 * HOUR - 2 * BAR)
        self.assertEqual(panel.deadline(decision, 48), panel.deadline(decision, 24))
        self.assertLessEqual(panel.deadline(decision, 72), decision + 72 * HOUR)
        self.assertIsNone(panel.deadline(monday + HOUR, 72))

    def test_exact_six_recipes_and_shared_risk(self):
        p = json.loads((ROOT / "research/roadmap9/protocol.json").read_text())
        recipes = json.loads((ROOT / "research/roadmap9/recipes.json").read_text())
        self.assertEqual(tuple(r["id"] for r in recipes), RECIPE_IDS)
        self.assertEqual({r["hypothesis"] for r in recipes}, {"H1", "H2", "H3"})
        for recipe in recipes:
            self.assertEqual(recipe["risk_limits"], p["limits"])
            self.assertEqual(recipe["cost_profile"], p["scenarios"])
            self.assertFalse(recipe["evaluation_and_stopping"]["promotion_allowed"])
        self.assertEqual(p["limits"]["capitalUsd"], 20000)
        self.assertEqual(p["limits"]["maxDrawdown"], 0.08)
        self.assertEqual(p["budget"]["reserved_after"], 65)

    def test_native_fork_exact_generation(self):
        self.assertEqual(
            (ROOT / "runtime30/ultimate_replay_roadmap9.js").read_text(),
            build_roadmap9_replay.build(),
        )

    def test_native_engine_parity_and_exit_guards(self):
        script = r"""
const assert=require('node:assert/strict');
const {data,protocol}=require('./tools/ultimate_fixtures.cjs').dataset();
const old=require('./runtime30/ultimate_replay_research.js');
const next=require('./runtime30/ultimate_replay_roadmap9.js');
const {exitAction}=require('./runtime30/roadmap9_exit.js');
const session=data.sessions[110];
const signal={id:'synthetic',symbol:'SPY',hypothesis:'CLOSED_CHANNEL',direction:1,
 at:session.open+300001,plannedEntryAt:session.open+600000,index:0,stopDistance:2,regime:.4,metadata:{}};
assert.deepEqual(next.replayCampaign(signal,data.series[0],data,protocol,'BASELINE',10,1),
 old.replayCampaign(signal,data.series[0],data,protocol,'BASELINE',10,1));
const at=signal.plannedEntryAt+3600000;
signal.metadata={roadmapExit:'VALUE_PARTIAL',roadmapOriginalDeadline:signal.at+72*3600000};
const row={mean:.001,mean_se:.001,lower:.001-1.645*.001,decision_at:at-299000,
 execution_at:at,available_at:at-299000,model_asof:at-3600000,latest_label_at:at-7200000,
 deadline_at:at+24*3600000};
assert.equal(exitAction(signal,at,10,false,{['SPY:'+at]:row}).quantity,5);
assert.equal(exitAction(signal,at,5,true,{['SPY:'+at]:row}),null);
assert.equal(exitAction(signal,at,10,false,{['SPY:'+at]:{...row,deadline_at:signal.at+73*3600000}}),null);
assert.throws(()=>exitAction(signal,at,10,false,{['SPY:'+at]:{...row,decision_at:at+1}}),/CAUSALITY/);
assert.throws(()=>exitAction(signal,at,10,false,{['SPY:'+at]:{...row,mean:NaN}}),/FORECAST/);
signal.metadata.roadmapExit='VALUE_TOTAL';
assert.equal(exitAction(signal,at,10,false,{['SPY:'+at]:row}).quantity,10);
console.log('PASS');
"""
        out = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_cash_calendar_costs_and_independent_auditor(self):
        script = r"""
const {data}=require('./tools/ultimate_fixtures.cjs').dataset();
const {run}=require('./tools/roadmap9_replay.cjs');
const shift=150*86400000;
data.sessions.push(...data.sessions.map(s=>({date:new Date(s.open+shift).toISOString().slice(0,10),open:s.open+shift,close:s.close+shift})));
for(const series of data.series)series.bars.push(...series.bars.map(b=>({...b,t:b.t+shift,end:b.end+shift,availableAt:b.availableAt+shift})));
const sessions=data.sessions.slice(110,130).filter((_,i)=>i%7<5);
data.cashDividends=[];
const p={universe:['SPY'],periods:{evaluation_start:sessions[0].date,evaluation_end:sessions.at(-1).date,
 validation_start:sessions[0].date,validation_end:sessions[6].date,
 test_start:sessions[7].date,test_end:sessions.at(-1).date},holding_maximum_hours:72,
 scenarios:{NOMINAL:{spread_bps:2,slippage_bps:2,commission_usd_per_share_per_side:.005,external_cost_usd_per_calendar_day:1}},
 limits:{capitalUsd:20000,riskFraction:.0025,openRiskFraction:.0025,grossFraction:.12,assetFraction:.12,dailyLoss:.02,maxDrawdown:.08}};
// Explicit synthetic closures, never an asserted real exchange calendar.
data.sessions=data.sessions.filter(s=>s.open<sessions[0].open||s.open>sessions.at(-1).open||sessions.some(x=>x.open===s.open));
for(const series of data.series)series.bars=series.bars.filter(b=>data.sessions.some(s=>s.open<=b.t&&b.t<s.close));
const report=run(p,data,{signals:{NOMINAL:{CASH:[]}},exit_forecasts:{}},'CASH','NOMINAL');
console.log(JSON.stringify({report,protocol:p,data}));
"""
        out = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        fixture = json.loads(out.stdout)
        result = audit_report(
            fixture["report"], fixture["protocol"], fixture["data"], "NOMINAL:CASH"
        )
        self.assertTrue(result["verified"])
        self.assertGreater(result["modeled_external_costs_usd"], result["sessions"])
        corrupt = copy.deepcopy(fixture["report"])
        corrupt["curve"][-1]["equity_end_usd"] += 1
        with self.assertRaises(ValueError):
            audit_report(corrupt, fixture["protocol"], fixture["data"], "NOMINAL:CASH")


if __name__ == "__main__":
    unittest.main()
