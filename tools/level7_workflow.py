"""One bounded offline workflow for HarpoonX's portfolio evidence target 7.

Reuses the causal-panel producer, economic v2 gate and forward attribution
verifier. It never fits models, reserves a trial, sends orders or deploys.
Missing resources are reported individually. A successful software run is not
financial acceptance. Existing result files cannot be overwritten by this CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "quant"))
from harpoon_quant.core import digest, finite, timestamp
from harpoon_quant.study_integrity import _json as strict_json
from harpoon_quant.forward_economics import bootstrap_forward_growth, epoch, need, summarize_observed_portfolio

SCHEMA = "HARPOON_LEVEL7_WORKFLOW_REQUEST_1"
AUTHORITY = {"execution_allowed": False, "liveApproved": False, "deployment_allowed": False,
             "financial_approval": False, "research_trials_created": 0, "models_fitted": 0}
REMEDIATIONS = {
    "CAUSAL_PANEL_REQUEST_MISSING": "Recoger snapshots prospectivos y fijar la selección antes de calibrar; usar tools/build_causal_panel.py.",
    "CAUSAL_PANEL_NOT_READY": "Acumular las sesiones causales que exige la calibración vigente, conservando rechazos y costes; no reconstruir recepción desde barras.",
    "ECONOMIC_PROTOCOL_MISSING": "Completar y registrar el protocolo V2 con universo, periodos, costes, historial de intentos y criterios congelados.",
    "ECONOMIC_EVIDENCE_MISSING": "Entregar el request de derivación V2: comparación C0/Ridge/SVR reejecutable, ledger y estrés ya registrados.",
    "MODELED_ECONOMIC_GATE_NOT_PASSED": "Resolver los bloqueos del gate V2 o rechazar la candidata; no cambiar los umbrales después del resultado.",
    "FORWARD_SPEC_MISSING": "Añadir forward_validation al protocolo ANTES de registrarlo, con identidad de cuenta, modelo, configuración y criterio económico.",
    "FORWARD_ATTRIBUTION_REQUEST_MISSING": "Recoger export inicial, export terminal y ledger completo. Vincular fills a intents, campañas y decisiones.",
    "FORWARD_ATTRIBUTION_NOT_VERIFIED": "Resolver cada enlace faltante con su evidencia original; el legado sin procedencia permanece desconocido.",
    "REAL_FORWARD_EXECUTION_REQUIRED": "Para acreditar rendimiento real se requiere evidencia REAL del periodo; PAPER se mantiene identificado como simulación.",
    "FORWARD_GROWTH_UNCERTAIN": "Conservar el resultado inconcluso y seguir el calendario preregistrado; no ampliar la muestra hasta que aparezca beneficio.",
    "FORWARD_RISK_NOT_MEASURABLE": "Restaurar observaciones, marcas y antigüedad de posiciones; no asumir exposición cero.",
    "FORWARD_FLOWS_OUTSIDE_COMPARISON_SCOPE": "El ledger calcula los flujos, pero el comparador actual empieza en efectivo sin aportaciones. Replicar el mismo calendario de flujos en todas las políticas antes de certificar la comparación.",
    "FORWARD_BOUNDARY_ECONOMIC_BRIDGE_REQUIRED": "Las marcas desplazadas son diagnósticas. Aportar valoración exacta en los límites comunes o una conciliación del intervalo omitido antes de certificar ese periodo.",
    "FORWARD_TRADING_ACTIVITY_NOT_DEMONSTRATED": "Faltan ejecuciones atribuibles a la candidata durante el periodo; no operar no demuestra rentabilidad de trading.",
}


def load_ref(ref: Any, base: Path, sources: list[dict[str, Any]]) -> tuple[Any, Path]:
    need(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "BOUND_FILE_REFERENCE_REQUIRED")
    need(isinstance(ref["path"], str) and isinstance(ref["sha256"], str) and len(ref["sha256"]) == 64,
         "BOUND_FILE_REFERENCE_REQUIRED")
    path = (base / ref["path"]).resolve()
    need(path.is_file() and path.stat().st_size <= 192 * 1024 * 1024, "SOURCE_SIZE_OR_TYPE")
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == ref["sha256"], "SOURCE_HASH_MISMATCH:" + path.name)
    sources.append({"path": os.path.relpath(path, base), "sha256": ref["sha256"], "bytes": len(raw)})
    need(sum(item["bytes"] for item in sources) <= 384 * 1024 * 1024, "WORKFLOW_TOTAL_SOURCE_BYTES")
    return strict_json(raw), path


def node_attribution(request: dict[str, Any], base: Path) -> dict[str, Any]:
    """Fixed verifier path; no caller-supplied executable and no network."""
    adjusted = json.loads(json.dumps(request, allow_nan=False))
    for key in ("ledger_bundle", "coordinator_export", "initial_coordinator_export"):
        if isinstance(adjusted.get(key), dict) and isinstance(adjusted[key].get("path"), str):
            adjusted[key]["path"] = str((base / adjusted[key]["path"]).resolve())
    with tempfile.TemporaryDirectory(prefix="harpoon-forward-") as tmp:
        folder = Path(tmp)
        source, target = folder / "request.json", folder / "result.json"
        source.write_text(json.dumps(adjusted, allow_nan=False), encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
               "HARPOON_QUANT_PYTHON": sys.executable, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
        try:
            result = subprocess.run(["node", str(APP / "tools/verify_forward_attribution.cjs"),
                                     "--input", str(source), "--output", str(target)],
                                    cwd=APP, env=env, shell=False, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("FORWARD_FIXED_VERIFIER_UNAVAILABLE") from exc
        need(target.is_file() and target.stat().st_size <= 192 * 1024 * 1024, "FORWARD_VERIFIER_NO_BOUNDED_RESULT")
        report = strict_json(target.read_bytes())
        need(result.returncode in (0, 2), "FORWARD_VERIFIER_PROCESS_FAILED")
        need(report.get("execution_allowed") is False and report.get("financial_acceptance_allowed") is False,
             "FORWARD_VERIFIER_AUTHORITY_CHANGED")
        return report


def validate_forward_spec(p: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    spec = p["forward_validation"]
    need(isinstance(spec, dict) and spec.get("schema") == "HARPOON_FORWARD_SPEC_1", "FORWARD_SPEC_SCHEMA")
    verifier_names = ("tools/level7_workflow.py", "tools/verify_forward_attribution.cjs",
                      "quant/harpoon_quant/forward_economics.py")
    need(spec.get("verifier_hashes") == {name: hashlib.sha256((APP / name).read_bytes()).hexdigest()
                                        for name in verifier_names}, "FORWARD_IMPLEMENTATION_NOT_PREREGISTERED")
    need(p["max_drawdown_fraction"] <= 0.08 and p["max_gross_exposure_fraction"] <= 0.5 and
         p["horizon_hours"] <= 72, "PROJECT_RISK_ENVELOPE_CANNOT_BE_INCREASED")
    expected = dict(spec["expected"])
    if expected.get("boundary_tolerance_ms") is not None:
        need(expected["boundary_tolerance_ms"] == spec["boundary_tolerance_ms"], "FORWARD_BOUNDARY_SPEC_MISMATCH")
    expected["boundary_tolerance_ms"] = spec["boundary_tolerance_ms"]
    need(expected.get("candidate_role") == "SVR", "FORWARD_CANDIDATE_MUST_MATCH_V2_SVR")
    need(expected.get("execution_nature") in ("PAPER", "REAL", "LIVE"), "FORWARD_EXECUTION_NATURE")
    need(expected.get("period") == {"start_at": epoch(p["period"]["test_start"]),
                                     "end_at": epoch(p["period"]["test_end"])}, "FORWARD_V2_PERIOD_MISMATCH")
    need(0 <= finite(spec["minimum_economic_pnl_usd"], "FORWARD_MIN_NET") and
         0 <= finite(spec["minimum_mean_log_growth"], "FORWARD_MIN_GROWTH"), "FORWARD_NEGATIVE_ECONOMIC_THRESHOLD")
    need(0 < finite(spec["family_alpha"], "FORWARD_ALPHA") and
         spec["family_alpha"] + p["statistics"]["family_alpha"] <= 0.05 + 1e-12,
         "COMBINED_COMPARISON_FORWARD_ALPHA_EXCEEDS_005")
    registration = gate.get("preregistration")
    need(isinstance(registration, dict) and registration.get("registered_at"), "FORWARD_REGISTRATION_UNVERIFIED")
    registered = epoch(registration["registered_at"])
    need(registered < expected["period"]["start_at"], "FORWARD_REGISTRATION_AFTER_START")
    if expected.get("registered_at") is not None:
        need(epoch(expected["registered_at"]) == registered, "FORWARD_REGISTRATION_TIME_MISMATCH")
    expected["registered_at"] = registered
    bindings = gate.get("derivation", {}).get("bindings") or {}
    runtime_predictor = (bindings.get("runtime_predictor_bindings") or {}).get("SVR") or {}
    need(expected.get("model_hash") == runtime_predictor.get("model_hash") and
         isinstance(expected.get("model_hash"), str), "FORWARD_MODEL_NOT_BOUND_TO_COMPARISON")
    need(expected.get("quant_config_hash") == runtime_predictor.get("quant_config_hash") and
         isinstance(expected.get("quant_config_hash"), str), "FORWARD_QUANT_CONFIG_NOT_BOUND_TO_COMPARISON")
    need(epoch(expected["model_available_at"]) == epoch(runtime_predictor.get("model_available_at")),
         "FORWARD_MODEL_AVAILABILITY_NOT_BOUND_TO_COMPARISON")
    need(expected.get("runtime_config_hash") == bindings.get("observed_runtime_config_hash") and
         isinstance(expected.get("runtime_config_hash"), str), "FORWARD_SOURCE_CONFIGURATION_NOT_BOUND_TO_COMPARISON")
    need(expected.get("account_id") == bindings.get("observed_account_id") and
         isinstance(expected.get("account_id"), str), "FORWARD_SOURCE_ACCOUNT_NOT_BOUND_TO_COMPARISON")
    need(epoch(expected["model_available_at"]) < registered, "FORWARD_MODEL_NOT_FROZEN_BEFORE_REGISTRATION")
    return expected


def evaluate(request: dict[str, Any], base: Path) -> dict[str, Any]:
    need(request.get("schema") == SCHEMA and request.get("target") == 7, "LEVEL7_WORKFLOW_SCHEMA")
    need(set(request) <= {"schema", "target", "panel_request", "economic_protocol", "economic_evidence",
                          "forward_attribution_request", "reference_note"}, "LEVEL7_UNKNOWN_REQUEST_FIELD")
    sources: list[dict[str, Any]] = []
    blockers: list[str] = []
    rejected: list[str] = []
    out: dict[str, Any] = {"schema": "HARPOON_LEVEL7_WORKFLOW_REPORT_1", "request_hash": digest(request),
        "target": 7, "level7_criterion_met": False, "economic_score": None,
        "score_meaning": "Hito documental de evidencia económica de la cartera; no probabilidad de ganar ni retorno futuro.",
        "dictamen": "VENTAJA_NO_DEMOSTRADA", "panel": None, "modeled_validation": None,
        "forward_attribution": None, "observed_portfolio": None, "forward_statistics": None,
        "blockers": blockers, "rejection_reasons": rejected, "sources": sources,
        "limitations": ["Local hashes do not independently authenticate a broker or clock.",
                        "Modeled Ridge/SVR superiority and observed account profit are separate requirements.",
                        "Risk is observed at retained ledger resolution, not guaranteed between observations.",
                        "A passed criterion never grants order or deployment authority.",
                        "No per-asset positive-return requirement; one continuous portfolio is the unit."], **AUTHORITY}
    if request.get("panel_request") is None:
        blockers.append("CAUSAL_PANEL_REQUEST_MISSING")
    else:
        try:
            from harpoon_quant.causal_panel import build
            panel_request, source = load_ref(request["panel_request"], base, sources)
            panel = build(panel_request, source.parent)
            out["panel"] = panel
            if (panel["panel"]["origin"] != "OBSERVED" or
                    panel["readiness"].get("status") != "PANEL_ADMISSIBLE_NOT_FINANCIALLY_VALIDATED" or
                    panel["readiness"].get("accepted_rows", 0) <= 0):
                blockers.append("CAUSAL_PANEL_NOT_READY")
        except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
            blockers.append("CAUSAL_PANEL:" + str(exc))
    p, gate = None, None
    if request.get("economic_protocol") is None:
        blockers.append("ECONOMIC_PROTOCOL_MISSING")
    if request.get("economic_evidence") is None:
        blockers.append("ECONOMIC_EVIDENCE_MISSING")
    if request.get("economic_protocol") and request.get("economic_evidence"):
        try:
            from harpoon_quant.economic_gate_v2 import evaluate as evaluate_v2
            p, _ = load_ref(request["economic_protocol"], base, sources)
            evidence, source = load_ref(request["economic_evidence"], base, sources)
            need(p.get("schema") == "HARPOON_ECONOMIC_PROTOCOL_2", "V2_PROTOCOL_REQUIRED")
            need(timestamp(evidence["generated_at"]) <= datetime.now(UTC), "EVIDENCE_GENERATION_IN_FUTURE")
            gate = evaluate_v2(p, evidence, source.parent)
            out["modeled_validation"] = gate
            if (out["panel"] and out["panel"]["artifact_hash"] !=
                    (gate.get("derivation") or {}).get("readiness", {}).get("components", {}).get("data", {}).get("artifact_hash")):
                blockers.append("CURRENT_PANEL_NOT_BOUND_TO_MODELED_VALIDATION")
            if gate.get("level5_criterion_met") is not True:
                blockers.append("MODELED_ECONOMIC_GATE_NOT_PASSED")
            if gate.get("dictamen") == "RECHAZADO":
                rejected.append("MODELED_CANDIDATE_REJECTED")
        except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
            blockers.append("MODELED_VALIDATION:" + str(exc))
    if not p or not p.get("forward_validation"):
        blockers.append("FORWARD_SPEC_MISSING")
    if request.get("forward_attribution_request") is None:
        blockers.append("FORWARD_ATTRIBUTION_REQUEST_MISSING")
    elif p and p.get("forward_validation") and gate:
        try:
            expected = validate_forward_spec(p, gate)
            forward_request, source = load_ref(request["forward_attribution_request"], base, sources)
            if forward_request.get("expected") is not None:
                need(forward_request["expected"] == expected, "CALLER_FORWARD_BINDINGS_DIFFER_FROM_PROTOCOL")
            forward_request["expected"] = expected
            forward = node_attribution(forward_request, source.parent)
            # Full original reconstructed ledger remains in the verifier result;
            # the workflow stores its hash and economic curve, avoiding duplicates.
            out["forward_attribution"] = {k: v for k, v in forward.items() if k not in {"ledger", "generated_at"}}
            out["forward_attribution"]["reconstructed_ledger_hash"] = digest(forward["ledger"]) if forward.get("ledger") else None
            if forward.get("verified") is not True:
                blockers.append("FORWARD_ATTRIBUTION_NOT_VERIFIED")
            if forward.get("executionNature") not in ("REAL", "LIVE"):
                blockers.append("REAL_FORWARD_EXECUTION_REQUIRED")
            # The verifier also reconciles late fills through end+tolerance.
            # Those fills must not manufacture trading activity inside the
            # exact economic period being assessed.
            period_start = epoch(p["period"]["test_start"])
            period_end = epoch(p["period"]["test_end"])
            attributed_fills = forward.get("attributions")
            period_fill_count = sum(
                1 for item in attributed_fills
                if isinstance(item, dict) and type(item.get("at")) is int
                and period_start < item["at"] <= period_end
            ) if isinstance(attributed_fills, list) else 0
            out["forward_attribution"]["evaluated_period_attributed_fill_count"] = period_fill_count
            if (type(forward.get("attributed_fill_count")) is not int or
                    forward["attributed_fill_count"] <= 0 or period_fill_count <= 0):
                blockers.append("FORWARD_TRADING_ACTIVITY_NOT_DEMONSTRATED")
            ledger = forward.get("ledger")
            if ledger:
                summary = summarize_observed_portfolio(ledger, p)
                out["observed_portfolio"] = {k: v for k, v in summary.items() if k != "log_returns"}
                if not summary["requested_period_boundaries_exact"]:
                    blockers.append("FORWARD_BOUNDARY_ECONOMIC_BRIDGE_REQUIRED")
                if summary["external_flow_event_count"] or summary["net_external_flows_usd"] != 0:
                    blockers.append("FORWARD_FLOWS_OUTSIDE_COMPARISON_SCOPE")
                if summary["insolvency"]:
                    rejected.append("OBSERVED_ACCOUNT_INSOLVENCY")
                if summary["economic_pnl_usd"] <= p["forward_validation"]["minimum_economic_pnl_usd"]:
                    rejected.append("OBSERVED_ECONOMIC_PNL_MINIMUM_NOT_MET")
                if summary["economic_drawdown_fraction_observed"] > p["max_drawdown_fraction"]:
                    rejected.append("OBSERVED_DRAWDOWN_LIMIT_EXCEEDED")
                if summary["maximum_gross_exposure_fraction_observed"] > p["max_gross_exposure_fraction"]:
                    rejected.append("OBSERVED_GROSS_EXPOSURE_LIMIT_EXCEEDED")
                risk = forward.get("risk") or {}
                holding = risk.get("maximum_observed_holding_hours")
                if type(holding) not in (int, float):
                    blockers.append("FORWARD_RISK_NOT_MEASURABLE")
                elif holding > p["horizon_hours"]:
                    rejected.append("OBSERVED_HOLDING_LIMIT_EXCEEDED")
                if not summary["insolvency"]:
                    stats = bootstrap_forward_growth(summary["log_returns"], p)
                    out["forward_statistics"] = stats
                    lower_pass = (stats["status"] == "COMPUTED" and
                                  all(b["lower_one_sided_mean_log_growth"] > p["forward_validation"]["minimum_mean_log_growth"]
                                      for b in stats["blocks"]))
                    if not lower_pass:
                        blockers.append("FORWARD_GROWTH_UNCERTAIN")
                    if stats["point_mean_log_growth"] <= p["forward_validation"]["minimum_mean_log_growth"]:
                        rejected.append("OBSERVED_GEOMETRIC_GROWTH_MINIMUM_NOT_MET")
            else:
                blockers.append("FORWARD_RECONSTRUCTED_LEDGER_MISSING")
        except (ValueError, TypeError, KeyError, OSError, AttributeError, OverflowError) as exc:
            blockers.append("FORWARD_VALIDATION:" + str(exc))
    if rejected:
        out["dictamen"] = "RECHAZADO"
    elif not blockers and out["forward_statistics"] is not None:
        out.update(level7_criterion_met=True, economic_score=7,
                   dictamen="CANDIDATO_PARA_VALIDACION_FORWARD",
                   observed_scope_only=True, ongoing_forward_monitoring_required=True)
    out["next_actions"] = [{"blocker": b, "remediation": REMEDIATIONS.get(b, "Revisar la causa y aportar la fuente original; volver a ejecutar sin cambiar resultados ni umbrales.")}
                           for b in dict.fromkeys(blockers)]
    names = ["tools/level7_workflow.py", "tools/verify_forward_attribution.cjs",
             "quant/harpoon_quant/forward_economics.py", "quant/harpoon_quant/economic_gate_v2.py"]
    out["implementation_hashes"] = {name: hashlib.sha256((APP / name).read_bytes()).hexdigest()
                                    if (APP / name).is_file() else None for name in names}
    out["artifact_hash"] = digest(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify", type=Path, help="Recompute and compare an existing report; write a separate receipt")
    args = parser.parse_args()
    need(not args.output.exists(), "OUTPUT_EXISTS_PRESERVE_PRIOR_RESULT")
    request = strict_json(args.input.read_bytes())
    result = evaluate(request, args.input.resolve().parent)
    if args.verify:
        original = strict_json(args.verify.read_bytes())
        result = {"schema": "HARPOON_LEVEL7_WORKFLOW_VERIFICATION_1", "verified": original == result,
                  "expected_artifact_hash": result["artifact_hash"],
                  "original_artifact_hash": original.get("artifact_hash"), **AUTHORITY}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(args.output.resolve()), "dictamen": result.get("dictamen"),
                      "level7_criterion_met": result.get("level7_criterion_met", False),
                      "verified": result.get("verified"), "blockers": result.get("blockers"), **AUTHORITY}))
    return 2 if result.get("verified") is False else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error), "level7_criterion_met": False, **AUTHORITY}), file=sys.stderr)
        raise SystemExit(2) from error
