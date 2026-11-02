#!/usr/bin/env python3
"""Execute the registered finite diagnostic family; no search or broker route."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "quant"))
sys.path.insert(0, str(APP / "tools"))
import quant8_register
from harpoon_quant import historical_bank as historical
from harpoon_quant import quant8_models, quant8_statistics
from audit_historical_results import audit_report


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_limits(base, protocol, policy):
    """Derive authorized caps independently of the self-reported replay limits."""
    limits = dict(base['limits'])
    if policy == 'HUBER_REGIME_CAP':
        fields = ['riskFraction', 'openRiskFraction', 'grossFraction', 'assetFraction']
        if protocol['regime_cap']['fields'] != fields or protocol['regime_cap']['limit_multiplier'] != .5:
            raise ValueError('FROZEN_HALF_CAP_REQUIRED')
        for field in fields:
            limits[field] *= .5
    return limits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=APP / "research/quant8/protocol.json")
    parser.add_argument("--manifest", type=Path, default=APP / "research/quant8/source_manifest.json")
    parser.add_argument("--registration-dir", type=Path, default=APP / "evidence/core_quant8_30_17_0/registration")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-against", type=Path)
    args = parser.parse_args()
    os.chdir(APP)
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_RETAIN_ALL_ATTEMPTS")
    out.mkdir(parents=True, exist_ok=True)
    record = {"schema": "HARPOON_QUANT8_RUN_1", "started_at": datetime.now(UTC).isoformat(),
        "status": "STARTED", "python": sys.version, "platform": platform.platform(), "financial_acceptance_allowed": False,
        "purpose": "EXACT_REPRODUCTION" if args.verify_against else "REGISTERED_DIAGNOSTIC", "steps": []}
    def save(name, value):
        historical.write(out / name, value)
    save("run_receipt.json", record)
    def command(name, cmd):
        env = {**os.environ, "PYTHONPATH": str(APP / "quant"), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        with (out / (name + ".log")).open("wb") as log:
            p = subprocess.run(cmd, cwd=APP, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        record["steps"].append({"name": name, "exit_code": p.returncode, "log_sha256": sha(out / (name + ".log"))})
        save("run_receipt.json", record)
        if p.returncode:
            raise RuntimeError("RETAINED_STEP_FAILURE:" + name)
        print(name + ":PASS", flush=True)
    try:
        registration = quant8_register.verify(args.registration_dir.resolve(), args.protocol.resolve(), args.manifest.resolve())
        save("registration_verification.json", registration)
        protocol = historical.read(args.protocol)
        base = historical.read(APP / protocol["base_protocol"])
        dataset = APP / protocol["dataset"]
        data = historical.read(dataset)
        command("01_data_audit", [sys.executable, "-B", "tools/historical_bank_data_audit.py", "--data-dir", str(dataset.parent), "--report", str(out / "data_audit.json")])
        command("02_prepare", ["node", "tools/quant8_replay.cjs", "prepare", str(args.protocol.resolve()), str(dataset), str(out)])
        signals, labels = historical.read(out / "signals.json"), historical.read(out / "training_labels.json")
        panel = historical.feature_panel(data, signals["signals"], base)
        # Runtime timings are not model input or a reproducibility artifact.
        panel.pop("benchmark", None)
        save("feature_panel.json", panel)
        legacy_models = historical.fit_fixed(panel, labels, base)
        save("legacy_models.json", legacy_models)
        save("legacy_admissions.json", historical.predict_fixed(panel, legacy_models, base))
        novel_models = quant8_models.fit_models(panel, labels, base, protocol)
        save("novel_models.json", novel_models)
        save("novel_admissions.json", quant8_models.predict(panel, novel_models, base, protocol))
        print("03_fixed_train_predict:PASS", flush=True)
        command("04_replay", ["node", "tools/quant8_replay.cjs", "replay", str(args.protocol.resolve()), str(dataset), str(out)])
        report_files = historical.read(out / "reports.json")
        reports = {k: historical.read(out / v) for k, v in report_files.items()}
        save("statistics.json", quant8_statistics.evaluate(reports, base, protocol))
        save("summary.json", {k: v["summary"] for k, v in reports.items()})
        audits = {}
        for key, report in reports.items():
            limits = expected_limits(base, protocol, key.split(':')[1])
            if report['portfolio']['limits'] != limits:
                raise ValueError('REGISTERED_RISK_LIMITS_MISMATCH:' + key)
            bound = {**base, "limits": limits}
            audits[key] = audit_report(report, bound, data, key)
        save("accounting_audit.json", {"verified": True, "reports": audits, "financial_acceptance_allowed": False})
        files = ["signals.json", "training_labels.json", "feature_panel.json", "legacy_models.json", "legacy_admissions.json", "novel_models.json", "novel_admissions.json", "derivation_verification.json", "statistics.json", "summary.json", "accounting_audit.json", *report_files.values()]
        hashes = {f: sha(out / f) for f in files}
        save("result_hashes.json", hashes)
        if args.verify_against:
            prior = historical.read(args.verify_against / "result_hashes.json")
            mismatch = [k for k in set(prior) | set(hashes) if prior.get(k) != hashes.get(k)]
            save("reproduction_verification.json", {"verified": not mismatch, "mismatches": sorted(mismatch), "files_compared": len(hashes), "new_policy_variants": 0})
            if mismatch:
                raise ValueError("EXACT_REPRODUCTION_MISMATCH")
        record.update(status="COMPLETE", completed_at=datetime.now(UTC).isoformat(), hashes=hashes)
        save("run_receipt.json", record)
        print("COMPLETE: all fourteen curves retained; economic acceptance forbidden", flush=True)
        return 0
    except Exception as exc:
        record.update(status="FAILED_RETAINED", error=str(exc), completed_at=datetime.now(UTC).isoformat())
        save("run_receipt.json", record)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
