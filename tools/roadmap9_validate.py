"""Execute scoped engineering tests and benchmark registered core snapshots.

No economic search or broker operation is performed. Results record individual
tests, skipped cases, elapsed time, environment and code hashes. The benchmark
uses a preregistered 288-context synthetic capacity profile and is not a broker SLA.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import resource
import sys
import time
import unittest
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "quant"))


def hashes(full_suite: bool = False) -> dict[str, str]:
    files = list((ROOT / "quant/harpoon_quant/roadmap9").glob("*.py"))
    files += list((ROOT / "quant/tests").glob("test_roadmap9*.py"))
    files += [Path(__file__).resolve()]
    if full_suite:
        for directory, suffixes in (("quant", {".py"}), ("tools", {".py", ".cjs", ".js"}),
                                   ("src", {".ts", ".js", ".cjs"}), ("runtime", {".py", ".js", ".cjs"}),
                                   ("runtime30", {".js", ".cjs"}), ("xxx", {".ts"}), ("config", {".json"})):
            files += [p for p in (ROOT / directory).rglob("*") if p.is_file() and p.suffix in suffixes]
        files += [ROOT / name for name in ("package.json", "package-lock.json") if (ROOT / name).is_file()]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.rows: list[dict[str, Any]] = []
        self.starts: dict[str, float] = {}

    def startTest(self, test: Any) -> None:
        self.starts[test.id()] = time.perf_counter()
        super().startTest(test)

    def record(self, test: Any, status: str, detail: str = "") -> None:
        self.rows.append({"test_id": test.id(), "result": status,
                          "seconds": time.perf_counter() - self.starts.get(test.id(), time.perf_counter()),
                          "detail": detail})

    def addSuccess(self, test: Any) -> None:
        self.record(test, "PASS")
        super().addSuccess(test)

    def addError(self, test: Any, err: Any) -> None:
        self.record(test, "ERROR", str(err[1]))
        super().addError(test, err)

    def addFailure(self, test: Any, err: Any) -> None:
        self.record(test, "FAIL", str(err[1]))
        super().addFailure(test, err)

    def addSkip(self, test: Any, reason: str) -> None:
        self.record(test, "SKIP", reason)
        super().addSkip(test, reason)

    def addExpectedFailure(self, test: Any, err: Any) -> None:
        self.record(test, "EXPECTED_FAILURE", str(err[1]))
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test: Any) -> None:
        self.record(test, "UNEXPECTED_SUCCESS")
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test: Any, subtest: Any, err: Any) -> None:
        if err is not None:
            self.record(subtest, "SUBTEST_FAIL", str(err[1]))
        super().addSubTest(test, subtest, err)


def run_tests(output: Path, full_suite: bool = False) -> dict[str, Any]:
    before = hashes(full_suite)
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    patterns = ("test*.py",) if full_suite else ("test_roadmap9*.py", "test_frontier*.py", "test_synthetic9*.py")
    for pattern in patterns:
        suite.addTests(loader.discover(str(ROOT / "quant/tests"), pattern=pattern))
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordingResult).run(suite)
    assert isinstance(result, RecordingResult)
    after = hashes(full_suite)
    report = {"schema": "HARPOON_ROADMAP_EXECUTED_TESTS_1", "tests_run": result.testsRun,
              "passed": sum(r["result"] == "PASS" for r in result.rows),
              "skipped": len(result.skipped), "failures": len(result.failures), "errors": len(result.errors),
              "successful": result.wasSuccessful() and before == after and not result.skipped,
              "sources_unchanged_during_execution": before == after, "source_sha256": after,
              "full_quant_suite": full_suite, "discovery_patterns": list(patterns),
              "python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform(),
              "test_results": result.rows, "execution_allowed": False,
              "scope": "SCOPED_UNIT_INTEGRATION_ADVERSARIAL_TESTS_NOT_EXTERNAL_AUDIT"}
    output.mkdir(parents=True, exist_ok=True)
    (output / "tests.log").write_text(log.getvalue())
    (output / "tests.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return report


def benchmark(output: Path, repeats: int) -> dict[str, Any]:
    """Measure all archived contexts under one frozen 81-action capacity fixture.

    The only state changes are max_new_lots=2 and available_buy_qty=2*lot_qty.
    These are declared synthetic capacity inputs, never observed liquidity. The
    core recipe, quotes, costs, risk limits, account cash and causal models stay
    unchanged. No strategy PnL is measured or selected by this benchmark.
    """
    import copy
    import gzip
    from collections import Counter
    from datetime import UTC, datetime

    from harpoon_quant.core import digest, timestamp
    from harpoon_quant.frontier.assurance import assure
    from harpoon_quant.frontier.contracts import Settings, require, validate_state
    from harpoon_quant.frontier.paths import fit
    from harpoon_quant.frontier_core import shadow
    from harpoon_quant.synthetic9.storage import load_gzip, verify_manifest

    require(type(repeats) is int and 1 <= repeats <= 3,
            "BENCHMARK_REPEATS_NOW_MEANS_FULL_288_CONTEXT_PASSES_USE_1_TO_3")
    output.mkdir(parents=True, exist_ok=True)

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def save_once(path: Path, raw: bytes) -> None:
        if path.exists():
            require(path.read_bytes() == raw, "IMMUTABLE_BENCHMARK_ARTIFACT:" + path.name)
        else:
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())

    def encoded(value: Any) -> bytes:
        return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()

    # Preserve the old two-snapshot benchmark; it never established V040.
    result_path = output / "benchmark.json"
    if result_path.exists():
        prior_raw = result_path.read_bytes()
        prior = json.loads(prior_raw)
        if prior.get("schema") == "HARPOON_ROADMAP_REGISTERED_PROFILE_BENCHMARK_1":
            save_once(output / "benchmark_before_v040.json", prior_raw)
        else:
            number = 1
            while (output / f"benchmark_reproduction_{number:03d}.json").exists():
                number += 1
            result_path = output / f"benchmark_reproduction_{number:03d}.json"

    directory = ROOT / "evidence/synthetic9/run_01"
    manifest = json.loads((directory / "manifest.json").read_text())
    verify_manifest(directory, ROOT, manifest)
    bank_protocol = json.loads((directory / "protocol.json").read_text())
    index = json.loads((directory / "account_index.json").read_text())
    accounts = sorted((r for r in index if r["strategy"] == "CORE"),
                      key=lambda r: (r["world"], r["seed"], r["cost_scenario"]))
    expected = {(w, s, c) for w in bank_protocol["worlds"]
                for s in bank_protocol["forward_seeds"] for c in bank_protocol["cost_scenarios"]}
    require(len(accounts) == 36 and {(r["world"], r["seed"], r["cost_scenario"])
            for r in accounts} == expected, "BENCHMARK_COMPLETE_SOURCE_MATRIX")
    markets: dict[str, dict[str, Any]] = {}
    models: dict[str, dict[str, Any]] = {}
    inputs: list[dict[str, Any]] = []
    source_files = {directory / "manifest.json", directory / "protocol.json",
                    directory / "account_index.json", Path(__file__).resolve()}
    source_files.update((ROOT / "quant/harpoon_quant/frontier").glob("*.py"))
    source_files.update(ROOT / p for p in ("quant/harpoon_quant/core.py",
        "quant/harpoon_quant/macd30.py", "quant/harpoon_quant/frontier_core.py",
        "quant/harpoon_quant/synthetic9/storage.py"))
    for account_meta in accounts:
        account_path = directory / account_meta["file"]
        account = load_gzip(account_path)
        source_files.add(account_path)
        market_name = f"markets/{account_meta['world']}_{account_meta['seed']}.json.gz"
        source_files.add(directory / market_name)
        if market_name not in markets:
            markets[market_name] = load_gzip(directory / market_name)
        dataset = markets[market_name]
        require(len(account["core_receipts"]) == bank_protocol["evaluation_weeks"],
                "BENCHMARK_ARCHIVED_DECISION_COVERAGE")
        for ordinal, archived in enumerate(account["core_receipts"]):
            cutoff, now = timestamp(archived["calibration_available_at"]), timestamp(archived["decision_at"])
            training = [r for r in dataset["samples"]
                if timestamp(r["known_at"]) < cutoff and timestamp(r["label_end"]) < now][-40:]
            require([r["id"] for r in training] == archived["training_ids"]
                    and max(r["known_at"] for r in training) == archived["maximum_training_known_at"],
                    "BENCHMARK_TRAINING_CAUSALITY")
            query_index = bank_protocol["warmup_weeks"] + ordinal
            query = dataset["samples"][query_index]
            require(query["start_at"] == archived["decision_at"], "BENCHMARK_QUERY_CLOCK")
            history = np.asarray([[np.log(r["ohlc"][j][-1][3]) for j in range(4)]
                for r in dataset["samples"][query_index - 8:query_index]])
            features = np.column_stack((history[-1], np.maximum(history.std(axis=0, ddof=1), 1e-5))).ravel()
            require(bool(np.allclose(features, query["features"], rtol=0, atol=1e-12)),
                    "BENCHMARK_CAUSAL_FEATURE_REBUILD")
            state = copy.deepcopy(archived["state"])
            require(state["features"] == query["features"]
                    and state["features_known_at"] == query["features_known_at"], "BENCHMARK_FEATURE_BINDING")
            require(len(state["assets"]) == 4 and all(a["current_lots"] == 0 for a in state["assets"]),
                    "BENCHMARK_FOUR_ASSET_FLAT_PROFILE")
            for asset in state["assets"]:
                asset["max_new_lots"] = 2
                asset["available_buy_qty"] = 2 * asset["lot_qty"]
            cfg = Settings(**archived["settings"])
            require(cfg.neighbors <= 40 and cfg.max_work <= 30_000_000,
                    "BENCHMARK_REGISTERED_WORK_LIMITS")
            info = validate_state(state, cfg)
            require(not info["pause_entries"], "BENCHMARK_CAPACITY_PROFILE_PAUSED")
            model_hash = archived["model_hash"]
            if model_hash not in models:
                model = fit({**dataset, "samples": training}, archived["calibration_available_at"], cfg)
                require(model["model_hash"] == model_hash, "BENCHMARK_REBUILT_MODEL_HASH")
                models[model_hash] = model
            require(0 < (now - cutoff).total_seconds() <= cfg.max_model_age_hours * 3600,
                    "BENCHMARK_MODEL_CLOCK")
            inputs.append({"world": account_meta["world"], "seed": account_meta["seed"],
                "scenario": account_meta["cost_scenario"], "week": ordinal,
                "source_account": str(account_path.relative_to(ROOT)), "source_receipt_index": ordinal,
                "original_state_sha256": digest(archived["state"]), "state": state,
                "state_sha256": digest(state), "model_hash": model_hash, "settings": archived["settings"],
                "training_ids": archived["training_ids"],
                "maximum_training_known_at": archived["maximum_training_known_at"],
                "calibration_available_at": archived["calibration_available_at"],
                "registered_action_count": 81,
                "expected_archived_status": archived["receipt"]["status"],
                "expected_archived_reason": archived["receipt"].get("reason")})
    inputs.sort(key=lambda r: (r["state"]["asof"], r["world"], r["seed"], r["scenario"]))
    require(len(inputs) == 288 and len({r["state_sha256"] for r in inputs}) == 288,
            "BENCHMARK_DISTINCT_INPUT_COVERAGE")
    bindings = {str(p.relative_to(ROOT)): sha(p) for p in sorted(source_files)}
    input_bytes = gzip.compress(encoded({"schema": "HARPOON_V040_CAPACITY_INPUTS_1", "inputs": inputs}),
                               compresslevel=9, mtime=0)
    save_once(output / "benchmark_inputs.json.gz", input_bytes)
    cpu_model = "UNREPORTED"
    cpu_info = Path("/proc/cpuinfo")
    if cpu_info.exists():
        cpu_model = next((line.split(":", 1)[1].strip() for line in cpu_info.read_text().splitlines()
                          if line.startswith("model name")), "UNREPORTED")
    hardware = {"architecture": platform.machine(), "cpu_model": cpu_model, "cpu_count": os.cpu_count(),
        "cpu_affinity_count": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "platform": platform.platform(), "python": platform.python_version(), "numpy": np.__version__,
        "blas_threads": os.environ.get("OPENBLAS_NUM_THREADS"), "omp_threads": os.environ.get("OMP_NUM_THREADS")}
    for name, path in (("cgroup_cpu_max", "/sys/fs/cgroup/cpu.max"),
                       ("cgroup_memory_max", "/sys/fs/cgroup/memory.max")):
        hardware[name] = Path(path).read_text().strip() if Path(path).exists() else "UNREPORTED"
    diversity = {"distinct_input_states": len({r["state_sha256"] for r in inputs}),
        "distinct_models": len(models), "distinct_market_windows": len({(r["world"], r["seed"], r["week"]) for r in inputs}),
        "distinct_feature_vectors": len({digest(r["state"]["features"]) for r in inputs}),
        "distinct_economic_state_inputs": len({digest({k: v for k, v in r["state"].items()
            if k not in {"account_binding", "version"}}) for r in inputs}),
        "worlds": dict(Counter(r["world"] for r in inputs)),
        "seeds": dict(Counter(str(r["seed"]) for r in inputs)),
        "cost_scenarios": dict(Counter(r["scenario"] for r in inputs)),
        "training_case_counts": dict(Counter(str(len(r["training_ids"])) for r in inputs)),
        "expected_controlled_rejections": dict(Counter(r["expected_archived_reason"] for r in inputs
            if r["expected_archived_status"] == "BLOCKED")),
        "flat_inventory_only": True, "cost_scenarios_share_market_windows": True,
        "independent_economic_observations_claimed": False}
    specification = {"schema": "HARPOON_V040_BENCHMARK_PROTOCOL_1", "validator_id": "V040",
        "profile_id": "SYN9_ALL_288_CONTEXTS_FOUR_ASSET_81_ACTION_CAPACITY_1",
        "origin": "SYNTHETIC_ENGINEERING_ONLY", "source_commit_declared": "df8b8334f3cb3e52f39fe2fbdee0b49ec76e6f32",
        "source_bindings": bindings, "input_archive_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "input_contexts": 288, "complete_passes": repeats, "measured_decisions": 288 * repeats,
        "selection_rule": "All 3 worlds x 4 original seeds x 3 cost scenarios x 8 original decision weeks; chronological then lexical order; no outcome selection",
        "fixture_changes": {"max_new_lots_each_asset": 2, "available_buy_qty_each_asset": "2 * native lot_qty"},
        "preserved": ["engine_recipe", "quotes", "fees", "slippage", "cash", "risk_limits", "features", "causal_training", "asof", "calendar"],
        "synthetic_capacity_is_not_observed_liquidity": True, "new_strategy_pnl_measurements": 0,
        "caps": {"assets": 4, "analogues": 40, "actions": 81, "work_units": 30_000_000},
        "acceptance": {"minimum_complete_decisions": 200, "p95_seconds": 2.0, "p99_seconds": 5.0,
            "unexpected_failures": 0, "input_fresh_at_completion": True, "selected_action_decimal_check": True},
        "work_unit_formula": "(2*enumerated_actions+4)*analogue_count*asset_count*72*3; same conservative bound enforced by core",
        "timing": "Full shadow() including state/model validation, prediction, finite-grid search, supervisor, source and receipt hashes; excludes artifact I/O, model fitting and subsequent independent Decimal audit",
        "warmups": 0, "quantile_method": "numpy.quantile(method=linear), complete decisions separately from all attempts",
        "freshness_clock": "Archived synthetic asof plus measured compute duration; not a claim the archived feed is current today",
        "diversity": diversity, "hardware": hardware, "execution_allowed": False}
    protocol_path = output / "benchmark_protocol.json"
    if protocol_path.exists():
        registered = json.loads(protocol_path.read_text())
        require({k: v for k, v in registered.items() if k != "registered_utc"} == specification,
                "BENCHMARK_PROFILE_ALREADY_FROZEN_DIFFERENTLY")
    else:
        registered = {**specification, "registered_utc": datetime.now(UTC).isoformat()}
        save_once(protocol_path, encoded(registered))
    protocol_hash = sha(protocol_path)
    print(json.dumps({"benchmark_profile_frozen": protocol_hash, "contexts": 288,
                      "passes": repeats, "maximum_actions": 81}), flush=True)
    measured: list[dict[str, Any]] = []
    decision_records: list[dict[str, Any]] = []
    started_utc = datetime.now(UTC).isoformat()
    for repetition in range(repeats):
        for ordinal, item in enumerate(inputs):
            state, model = item["state"], models[item["model_hash"]]
            cfg = Settings(**item["settings"])
            row = {"input_index": ordinal, "pass": repetition + 1, "state_sha256": item["state_sha256"],
                   "model_hash": item["model_hash"], "world": item["world"], "scenario": item["scenario"],
                   "seed": item["seed"], "week": item["week"], "errors": []}
            begun = time.perf_counter()
            try:
                decision = shadow(state, model, cfg)
                elapsed = time.perf_counter() - begun
                row.update(seconds=elapsed, status=decision["status"], reason=decision.get("reason"),
                           receipt_hash=decision["receipt_hash"])
                require(decision.get("execution_allowed") is False and decision.get("liveApproved") is False
                        and decision.get("level9_accredited") is False, "BENCHMARK_AUTHORITY")
                require(digest(state) == item["state_sha256"], "BENCHMARK_INPUT_MUTATED")
                now = timestamp(state["asof"])
                quote_age = max((now - timestamp(a[field])).total_seconds() for a in state["assets"]
                                for field in ("quote_at", "quote_received_at", "status_known_at"))
                model_age = (now - timestamp(model["available_at"])).total_seconds()
                label_age = (now - timestamp(item["maximum_training_known_at"])).total_seconds()
                freshness_left = min(cfg.max_quote_age_seconds - quote_age,
                    cfg.max_model_age_hours * 3600 - model_age, cfg.max_model_age_hours * 3600 - label_age)
                row.update(max_quote_age_seconds_at_completion=quote_age + elapsed,
                    model_age_seconds_at_completion=model_age + elapsed,
                    latest_training_label_age_seconds_at_completion=label_age + elapsed,
                    remaining_input_validity_seconds=freshness_left - elapsed,
                    input_fresh_at_completion=elapsed <= freshness_left)
                require(row["input_fresh_at_completion"], "BENCHMARK_INPUT_EXPIRED_DURING_COMPUTE")
                if decision["status"] == "SUPERVISED_RESEARCH_PROPOSAL":
                    actions, cases = decision["enumerated_actions"], len(decision["case_ids"])
                    work = (2 * actions + 4) * cases * len(state["assets"]) * 72 * 3
                    require(actions == 81 and 20 <= cases <= 40 and work <= 30_000_000,
                            "BENCHMARK_MEASURED_PROFILE_OR_WORK_LIMIT")
                    audit = assure(state, model, decision, cfg)
                    require(audit["verified"] is True, "BENCHMARK_DECIMAL_CHECK")
                    row.update(actions=actions, analogue_count=cases, work_units_upper_bound=work,
                               selected_action_decimal_verified=True, controlled_rejection=False)
                    decision_records.append({"input_index": ordinal, "pass": repetition + 1,
                                             "decision": decision, "decimal_audit": audit})
                else:
                    require(decision["status"] == item["expected_archived_status"] == "BLOCKED"
                            and decision.get("reason") == item["expected_archived_reason"] == "REGIME_DRIFT",
                            "BENCHMARK_UNEXPECTED_BLOCKED_DECISION")
                    row.update(actions=None, analogue_count=None, work_units_upper_bound=None,
                               selected_action_decimal_verified=False, controlled_rejection=True)
                    decision_records.append({"input_index": ordinal, "pass": repetition + 1, "decision": decision})
            except (ValueError, KeyError, TypeError, RuntimeError, ArithmeticError, OSError) as exc:
                row.setdefault("seconds", time.perf_counter() - begun)
                row["errors"].append(type(exc).__name__ + ":" + str(exc))
            measured.append(row)
            if (ordinal + 1) % 36 == 0:
                print(json.dumps({"benchmark_pass": repetition + 1, "attempted": ordinal + 1,
                    "unexpected_failures_so_far": sum(bool(r["errors"]) for r in measured)}), flush=True)
    complete = [r for r in measured if r.get("selected_action_decimal_verified") and not r["errors"]]

    def quantiles(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"count": 0, "p50_seconds": None, "p95_seconds": None, "p99_seconds": None, "maximum_seconds": None}
        samples = np.asarray([r["seconds"] for r in rows])
        p50, p95, p99 = np.quantile(samples, [0.5, 0.95, 0.99], method="linear")
        return {"count": len(rows), "p50_seconds": float(p50), "p95_seconds": float(p95),
                "p99_seconds": float(p99), "maximum_seconds": float(samples.max())}

    completed_quantiles = quantiles(complete)
    source_unchanged = all(sha(ROOT / p) == h for p, h in bindings.items())
    failures = [r for r in measured if r["errors"]]
    success = (len(complete) >= 200 and len(measured) == 288 * repeats and not failures and source_unchanged
        and completed_quantiles["p95_seconds"] <= 2 and completed_quantiles["p99_seconds"] <= 5)
    decisions_raw = gzip.compress(encoded({"protocol_sha256": protocol_hash, "receipts": decision_records}),
                                  compresslevel=9, mtime=0)
    decisions_path = result_path.with_name(result_path.stem + "_decisions.json.gz")
    save_once(decisions_path, decisions_raw)
    report = {"schema": "HARPOON_ROADMAP_REGISTERED_PROFILE_BENCHMARK_2", "validator_id": "V040",
        "profile": specification["profile_id"], "origin": "SYNTHETIC_ENGINEERING_ONLY",
        "protocol_file": protocol_path.name, "protocol_sha256": protocol_hash,
        "protocol_registered_utc": registered["registered_utc"], "measurements_started_utc": started_utc,
        "finished_utc": datetime.now(UTC).isoformat(), "source_commit_declared": specification["source_commit_declared"],
        "source_bindings": bindings, "sources_unchanged_during_execution": source_unchanged,
        "input_archive_sha256": specification["input_archive_sha256"], "diversity": diversity,
        "complete_passes": repeats, "total_decisions_attempted": len(measured), "complete_decisions": len(complete),
        "controlled_rejections": dict(Counter(r.get("reason") for r in measured if r.get("controlled_rejection"))),
        "unexpected_failure_count": len(failures), "failures": failures,
        "complete_decision_latency": completed_quantiles, "all_attempt_latency": quantiles(measured),
        "maximum_work_units_upper_bound": max((r.get("work_units_upper_bound") or 0 for r in measured), default=0),
        "maximum_quote_age_seconds_at_completion": max((r.get("max_quote_age_seconds_at_completion", 0) for r in measured), default=0),
        "minimum_remaining_input_validity_seconds": min((r.get("remaining_input_validity_seconds", -1) for r in measured), default=-1),
        "hardware": hardware, "process_peak_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "peak_rss_unit": "bytes" if sys.platform == "darwin" else "KiB", "samples": measured,
        "decision_receipts_file": decisions_path.name, "decision_receipts_sha256": hashlib.sha256(decisions_raw).hexdigest(),
        "success": bool(success), "verdict": "PASS" if success else "BLOCKED",
        "scope": "288_ARCHIVED_SYNTHETIC_CONTEXTS_WITH_DECLARED_TWO_LOT_CAPACITY;EMPIRICAL_LOCAL_CALCULATION_QUANTILES;FLAT_INVENTORY_ONLY;NOT_BROKER_SLA_OR_ALL_WORKLOADS",
        "not_measured": ["live_feed_or_broker_latency", "model_refit_latency", "holding_inventory_workloads",
            "other_universes", "distribution_free_tail_bound", "economic_profitability"],
        "new_strategy_pnl_measurements": 0, "execution_allowed": False, "level9_accredited": False}
    raw = encoded(report)
    if result_path.name == "benchmark.json" and result_path.exists():
        # The only overwrite is the preserved legacy two-snapshot receipt above.
        require(json.loads(result_path.read_text())["schema"] == "HARPOON_ROADMAP_REGISTERED_PROFILE_BENCHMARK_1",
                "BENCHMARK_RECEIPT_REPLACEMENT_FORBIDDEN")
        result_path.write_bytes(raw)
    else:
        save_once(result_path, raw)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--benchmark-only", action="store_true")
    parser.add_argument("--full-suite", action="store_true", help="Discover all quant tests once and hash their code dependencies")
    parser.add_argument("--repeats", type=int, default=1,
                        help="Complete passes over all 288 frozen contexts, 1 to 3; default 1")
    args = parser.parse_args()
    summary: dict[str, Any] = {}
    if not args.benchmark_only:
        tests = run_tests(args.output, full_suite=args.full_suite)
        summary.update(tests=tests["tests_run"], successful=tests["successful"], skipped=tests["skipped"])
    if args.benchmark or args.benchmark_only:
        report = benchmark(args.output, args.repeats)
        summary["benchmark_pass"] = report["success"]
    print(json.dumps(summary))
    if summary.get("successful") is False or summary.get("benchmark_pass") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
