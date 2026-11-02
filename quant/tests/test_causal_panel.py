"""Synthetic source contracts only: no calibration, broker or financial trial."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_runtime_observations import runtime_fixture

from harpoon_quant.bridge import from_runtime
from harpoon_quant.causal_panel import _split, build, sha, verify
from harpoon_quant.core import digest

FIRST = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)


def source_runtime(day: int, seconds: int = 0) -> dict:
    raw = runtime_fixture()
    now = FIRST + timedelta(days=day, seconds=seconds)
    raw["now"] = int(now.timestamp() * 1000)
    raw["config"].update(mode="paper", expected_account_id="SYNTHETIC-PANEL-ACCOUNT")
    for values in raw["market"]["bars"].values():
        for bar in values:
            bar["t"] = (datetime.fromisoformat(bar["t"]) + timedelta(days=day)).isoformat()
    for session in raw["market"]["calendar"]:
        session["open"] = int(session["open"] + day * 86400000)
        session["close"] = int(session["close"] + day * 86400000)
        session["date"] = datetime.fromtimestamp(session["open"] / 1000, UTC).date().isoformat()
    for quote in raw["market"]["quotes"].values():
        quote.update(at=raw["now"] - 1, received=raw["now"], bid=100.34 + day, ask=100.36 + day)
    return raw


def frame(day: int, seconds: int = 0) -> dict:
    raw = source_runtime(day, seconds)
    return {"schema": "HARPOON_PROSPECTIVE_FRAME_1", "account_id": raw["config"]["expected_account_id"],
            "data_origin": "SYNTHETIC_ENGINEERING_ONLY", "external_authenticity_verified": False,
            "runtime_input": raw, "observation": from_runtime(raw, None, observation_only=True),
            "session_context": {}, "sampled_execution_depth": None,
            "policy_parity_verified": False, "financial_acceptance_allowed": False}


def write_export(root: Path, frames: list[dict], *, offset: int = 0, total: int | None = None) -> dict:
    path = root / "capture.json"
    bundle = {"schema": "HARPOON_OBSERVATION_EXPORT_1", "account_id": "SYNTHETIC-PANEL-ACCOUNT",
              "head": "SYNTHETIC_EXPORT_BINDING", "offset": offset, "next_offset": offset + len(frames),
              "total_frames": len(frames) if total is None else total, "frames": frames,
              "liveApproved": False, "execution_allowed": False}
    path.write_text(json.dumps(bundle))
    code = """const fs=require('node:fs'),crypto=require('node:crypto');
const p=process.argv[1],x=JSON.parse(fs.readFileSync(p,'utf8'));
for(const f of x.frames){delete f.source_frame_sha256;f.source_frame_sha256=crypto.createHash('sha256').update(JSON.stringify(f)).digest('hex');}
fs.writeFileSync(p,JSON.stringify(x));"""
    subprocess.run(["node", "-e", code, str(path)], check=True, capture_output=True, timeout=10)
    return {"path": path.name, "sha256": sha(path)}


def request(source: dict | None = None) -> dict:
    return {"schema": "HARPOON_CAUSAL_PANEL_REQUEST_1", "available_at": "2026-10-18T14:50:01+00:00",
            "config": {"horizon_hours": 24}, "split_contract": "CURRENT_SVR_60_20_20_PURGED",
            "observation_exports": [source] if source else [],
            "selection": {"kind": "FIRST_CAUSAL_FRAME_AT_OR_AFTER_LOCAL_GRID", "timezone": "America/New_York",
                          "local_time": "10:50", "max_selection_delay_ms": 60000,
                          "label_quote_max_age_ms": 15000, "label_maturity_max_delay_ms": 120000}}


def synthetic_archive(root: Path) -> dict:
    """Tiny fake provider archive; never observational evidence."""
    raw = source_runtime(0)
    vector = from_runtime(raw, None, observation_only=True)["observations"][0]["features"]
    payload = {"request": {"timeframe": "5Min", "feed": "sip"}, "bars": {}, "counts": {"per_symbol": {}}}
    for symbol, history in raw["market"]["bars"].items():
        payload["bars"][symbol] = [{"symbol": symbol, "timestamp": b["t"], "open": b["o"], "high": b["h"],
            "low": b["l"], "close": b["c"], "volume": b["v"], "vwap": b["vw"]} for b in history]
        payload["counts"]["per_symbol"][symbol] = len(history)
    calendar = {"calendar": [{"date": s["date"], "open": datetime.fromtimestamp(s["open"] / 1000, UTC).isoformat(),
                              "close": datetime.fromtimestamp(s["close"] / 1000, UTC).isoformat()}
                             for s in raw["market"]["calendar"]]}
    from harpoon_quant.core import FEATURES
    diagnostic = {"schema": "HARPOON_BAR_DIAGNOSTIC_PANEL_NOT_CALIBRATION", "feature_names": list(FEATURES),
        "rows": [{"symbol": symbol, "observation_grid_at": FIRST.isoformat(), "phase": "OPENING_90",
                  "feature_values": {name: None if name in {"vwap_z", "spread_fraction"} else value
                                     for name, value in zip(FEATURES, vector, strict=True)}}
                 for symbol in payload["bars"]]}
    quote = raw["market"]["quotes"]["A"]
    quotes = {"schema": "HARPOON_L1_HISTORICAL_RETRIEVAL_1", "observed_at_utc": "2026-10-17T00:00:00+00:00",
              "original_runtime_receipt_times_available": False, "data_nature": "SYNTHETIC_ENGINEERING_ONLY",
              "payload": {"request": {"feed": "sip", "end": FIRST.isoformat()}, "counts": {"per_symbol": {}}, "quotes": {}}}
    for symbol in payload["bars"]:
        quotes["payload"]["counts"]["per_symbol"][symbol] = 1
        quotes["payload"]["quotes"][symbol] = [{"timestamp": datetime.fromtimestamp(quote["at"] / 1000, UTC).isoformat(),
            "bid_price": quote["bid"], "ask_price": quote["ask"], "bid_size": 20, "ask_size": 30}]
    def write(name, value):
        path = root / name
        path.write_text(json.dumps(value))
        return {"path": name, "sha256": sha(path)}
    refs = [write("bars.json", payload), write("calendar.json", calendar)]
    manifest = {"algorithm": "SHA-256", "files": [{"name": r["path"], "sha256": r["sha256"],
                 "bytes": (root / r["path"]).stat().st_size} for r in refs]}
    return {"manifest": write("manifest.json", manifest), "diagnostic_panel": write("diagnostic.json", diagnostic),
            "quotes": [write("quotes.json", quotes)], "start_date": calendar["calendar"][0]["date"],
            "end_date": FIRST.date().isoformat()}


class CausalPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_observed_resources_are_explicitly_blocked_without_training(self):
        result = build(request(), self.root)
        self.assertEqual(result["counts"]["causal_rows_admissible"], 0)
        self.assertEqual(result["readiness"]["status"], "MEDICION_BLOQUEADA")
        self.assertIn("PROSPECTIVE_OBSERVATION_EXPORTS_MISSING", result["blocking_resources"])
        self.assertIsNone(result["models"])
        self.assertFalse(result["training_executed"])
        self.assertFalse(result["execution_allowed"])

    def test_actual_engine_features_and_matured_price_label_form_common_panel(self):
        source = write_export(self.root, [frame(0), frame(1)])
        result = build(request(source), self.root)
        self.assertEqual(result["counts"]["causal_rows_admissible"], 1)
        self.assertEqual(result["panel"]["origin"], "SYNTHETIC_ENGINEERING_ONLY")
        row = result["panel"]["rows"][0]
        self.assertEqual(row["features"], frame(0)["observation"]["observations"][0]["features"])
        self.assertAlmostEqual(row["target_return"], 101.35 / 100.35 - 1)
        self.assertEqual(row["label_end"], "2026-10-16T14:50:00+00:00")
        self.assertEqual(row["label_known_at"], row["label_end"])
        self.assertFalse(row["label_source"]["is_fill_or_trade_pnl"])
        self.assertFalse(result["financial_acceptance_allowed"])
        self.assertFalse(result["panel"]["provenance"]["latency_measurement_allowed"])

    def test_file_hash_tampering_is_rejected(self):
        source = write_export(self.root, [frame(0), frame(1)])
        with (self.root / source["path"]).open("a") as handle:
            handle.write(" ")
        with self.assertRaisesRegex(ValueError, "SOURCE_HASH_MISMATCH"):
            build(request(source), self.root)

    def test_frame_hash_tampering_is_rejected_even_after_file_hash_updates(self):
        source = write_export(self.root, [frame(0), frame(1)])
        path = self.root / source["path"]
        payload = json.loads(path.read_text())
        payload["frames"][0]["observation"]["observations"][0]["features"][0] += .1
        path.write_text(json.dumps(payload))
        source["sha256"] = sha(path)
        with self.assertRaisesRegex(ValueError, "FRAME_HASH_VERIFICATION_FAILED"):
            build(request(source), self.root)

    def test_resealed_wrong_features_fail_recomputation_against_real_core(self):
        first = frame(0)
        first["observation"]["observations"][0]["features"][0] += .1
        source = write_export(self.root, [first, frame(1)])
        with self.assertRaisesRegex(ValueError, "FEATURE_RECOMPUTATION_MISMATCH"):
            build(request(source), self.root)

    def test_future_quote_does_not_become_a_causal_feature_row(self):
        first = frame(0)
        first["runtime_input"]["market"]["quotes"]["A"]["at"] = first["runtime_input"]["now"] + 1
        result = build(request(write_export(self.root, [first, frame(1)])), self.root)
        self.assertEqual(result["counts"]["causal_rows_admissible"], 0)
        self.assertTrue(any("QUOTE_NOT_KNOWN" in r["reason"] for r in result["rejections"]))

    def test_missing_quote_receipt_is_not_backdated_or_filled_with_zero(self):
        first = frame(0)
        del first["runtime_input"]["market"]["quotes"]["A"]["received"]
        result = build(request(write_export(self.root, [first, frame(1)])), self.root)
        self.assertEqual(result["counts"]["causal_rows_admissible"], 0)
        self.assertTrue(any("INTEGER_MILLISECOND_CLOCK_REQUIRED" in r["reason"] for r in result["rejections"]))

    def test_label_after_horizon_is_not_substituted_for_missing_asof_price(self):
        result = build(request(write_export(self.root, [frame(0), frame(1, 20)])), self.root)
        self.assertEqual(result["counts"]["causal_rows_admissible"], 0)
        self.assertTrue(any("NO_NEAREST_FUTURE_PRICE" in r["reason"] for r in result["rejections"]))

    def test_first_row_selection_precedes_label_availability_and_is_not_rechosen(self):
        # The second decision would have an exact observed label; the first does
        # not. The adapter must retain the preselected first and reject its label.
        source = write_export(self.root, [frame(0), frame(0, 20), frame(1, 20)])
        result = build(request(source), self.root)
        self.assertEqual(result["counts"]["causal_rows_admissible"], 0)
        self.assertTrue(any(r["stage"] == "label" and r["at"] == FIRST.isoformat() for r in result["rejections"]))

    def test_partial_export_and_reordered_frames_are_rejected(self):
        source = write_export(self.root, [frame(0)], total=2)
        with self.assertRaisesRegex(ValueError, "COMPLETE_EXPORT_REQUIRED"):
            build(request(source), self.root)
        source = write_export(self.root, [frame(1), frame(0)])
        with self.assertRaisesRegex(ValueError, "FRAME_CLOCK_NOT_INCREASING"):
            build(request(source), self.root)

    def test_duplicate_json_keys_are_rejected_before_frame_verification(self):
        path = self.root / "capture.json"
        path.write_text('{"frames":[],"frames":[]}')
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY:frames"):
            build(request({"path": path.name, "sha256": sha(path)}), self.root)

    def test_nonfinite_json_is_rejected_before_frame_verification(self):
        path = self.root / "capture.json"
        path.write_text('{"frames":[],"unknown":NaN}')
        with self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
            build(request({"path": path.name, "sha256": sha(path)}), self.root)

    def test_report_resealed_with_changed_admissibility_fails_source_reexecution(self):
        req = request(write_export(self.root, [frame(0), frame(1)]))
        result = build(req, self.root)
        altered = copy.deepcopy(result)
        altered["counts"]["causal_rows_admissible"] = 1000
        altered["artifact_hash"] = digest({k: v for k, v in altered.items() if k != "artifact_hash"})
        self.assertTrue(verify(result, req, self.root)["verified"])
        self.assertFalse(verify(altered, req, self.root)["verified"])

    def test_relocation_with_relative_sources_preserves_entire_receipt(self):
        req = request(write_export(self.root, [frame(0), frame(1)]))
        result = build(req, self.root)
        with tempfile.TemporaryDirectory() as location:
            other = Path(location)
            shutil.copyfile(self.root / "capture.json", other / "capture.json")
            relocated = build(req, other)
        self.assertEqual(result, relocated)
        self.assertEqual(result["source_hashes"][0]["path"], "capture.json")

    def test_shared_split_purges_labels_that_arrive_after_next_segment(self):
        start = datetime(2026, 1, 1, 14, tzinfo=UTC)
        rows = [{"row_id": str(day), "session": (start + timedelta(days=day)).date().isoformat(),
                 "label_end": (start + timedelta(days=day + 1)).isoformat(),
                 "label_known_at": (start + timedelta(days=day + 1)).isoformat()} for day in range(10)]
        rows[0]["label_known_at"] = "2026-01-07T00:00:00+00:00"
        split = _split(rows)
        self.assertIn("0", split["row_ids"]["purged"])
        self.assertNotIn("0", split["row_ids"]["training"])
        self.assertFalse(split["existing_ridge_internal_split_parity_certified"])

    def test_historical_complete_vectors_never_enter_admissible_panel(self):
        req = request()
        req["archive"] = synthetic_archive(self.root)
        result = build(req, self.root)
        self.assertEqual(result["counts"]["reconstructed_feature_rows"], 2)
        self.assertEqual(result["counts"]["causal_rows_admissible"], 0)
        self.assertEqual(result["panel"]["rows"], [])
        for row in result["archive_audit"]["reconstructed_rows"]:
            self.assertEqual(len(row["feature_values"]), 8)
            self.assertTrue(all(isinstance(x, float) for x in row["feature_values"].values()))
            self.assertIsNone(row["features_known_at"])
            self.assertIsNone(row["source_quote"]["original_received_at"])
            self.assertIsNone(row["source_quote"]["executable_depth"])
            self.assertFalse(row["training_ready"])
        self.assertFalse(result["archive_audit"]["prices_observed_but_original_availability_missing"])

    def test_backfill_cannot_claim_original_runtime_receipts(self):
        req = request()
        req["archive"] = synthetic_archive(self.root)
        path = self.root / "quotes.json"
        source = json.loads(path.read_text())
        source["original_runtime_receipt_times_available"] = True
        path.write_text(json.dumps(source))
        req["archive"]["quotes"][0]["sha256"] = sha(path)
        with self.assertRaisesRegex(ValueError, "HISTORICAL_QUOTE_SOURCE_CONTRACT"):
            build(req, self.root)

    def test_historical_report_cannot_be_resealed_to_promote_numeric_rows(self):
        req = request()
        req["archive"] = synthetic_archive(self.root)
        result = build(req, self.root)
        altered = copy.deepcopy(result)
        altered["panel"]["rows"] = altered["archive_audit"]["reconstructed_rows"]
        altered["counts"]["causal_rows_admissible"] = 2
        altered["artifact_hash"] = digest({k: v for k, v in altered.items() if k != "artifact_hash"})
        self.assertFalse(verify(altered, req, self.root)["verified"])

    def test_relocated_archive_keeps_paths_and_quote_source_hashes_stable(self):
        req = request()
        req["archive"] = synthetic_archive(self.root)
        result = build(req, self.root)
        with tempfile.TemporaryDirectory() as location:
            other = Path(location)
            for source in self.root.iterdir():
                shutil.copyfile(source, other / source.name)
            relocated = build(req, other)
        self.assertEqual(result, relocated)
        self.assertEqual(result["archive_audit"]["reconstructed_rows"][0]["source_quote"]["file"], "quotes.json")


if __name__ == "__main__":
    unittest.main()
