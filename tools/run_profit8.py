#!/usr/bin/env python3
"""Freeze and execute one bounded, historical PROFIT8 research cycle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "quant"), str(ROOT / "tools")]
from harpoon_quant.profit8.study import (
    attach_teachers,
    build_rows,
    make_bundle,
    statistics,
)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def read(path: Path) -> Any:
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def write(path: Path, value: Any, *, compressed: bool = False) -> None:
    raw = payload(value)
    if compressed:
        raw = gzip.compress(raw, compresslevel=9, mtime=0)
    if path.exists():
        require(path.read_bytes() == raw, "IMMUTABLE_OUTPUT_CHANGED:" + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def source_files() -> list[Path]:
    frozen = read(ROOT / "evidence/roadmap9/research/source_bindings.json")
    files = {
        ROOT / key.removeprefix("code:") for key in frozen if key.startswith("code:")
    }
    files.update((ROOT / "quant/harpoon_quant/profit8").glob("*.py"))
    files.update((ROOT / "quant/tests").glob("test_profit8*.py"))
    files.update((ROOT / "tools").glob("*profit8*.*"))
    files.update(
        {
            ROOT / name
            for name in (
                "runtime30/profit8_replay.js",
                "tools/residual_data_audit.py",
                "tools/verify_roadmap9_portfolio.py",
                ".github/workflows/profit8.yml",
            )
        }
    )
    require(all(p.is_file() for p in files), "ALL_BOUND_SOURCES_REQUIRED")
    return sorted(files)


def freeze() -> dict[str, Any]:
    protocol_path = ROOT / "research/profit8/protocol.json"
    recipes_path = ROOT / "research/profit8/recipes.json"
    protocol = read(protocol_path)
    require(
        sha(ROOT / protocol["base_dataset"]) == protocol["base_dataset_sha256"],
        "ORIGINAL_DATASET_HASH",
    )
    old = read(ROOT / "evidence/roadmap9/research/source_bindings.json")
    for key, expected in old.items():
        if key.startswith("code:"):
            require(
                sha(ROOT / key[5:]) == expected,
                "PRIOR_SCIENTIFIC_SOURCE_CHANGED:" + key,
            )
    path = ROOT / protocol.get("source_freeze", "research/profit8/source_freeze.json")
    sources = {str(p.relative_to(ROOT)): sha(p) for p in source_files()}
    body = {
        "schema": "HARPOON_PROFIT8_SOURCE_FREEZE_1",
        "sources": sources,
        "protocol_sha256": sha(protocol_path),
        "recipes_sha256": sha(recipes_path),
        "base_dataset_sha256": protocol["base_dataset_sha256"],
        "budget": protocol["budget"],
        "independent_preregistration": False,
        "historical_outcomes_computed_at_freeze": False,
        "frozen_at": now(),
    }
    if path.exists():
        existing = read(path)
        body["frozen_at"] = existing["frozen_at"]
    write(path, body)
    return body


def verify_freeze() -> dict[str, Any]:
    protocol = read(ROOT / "research/profit8/protocol.json")
    frozen = read(
        ROOT / protocol.get("source_freeze", "research/profit8/source_freeze.json")
    )
    for name, expected in frozen["sources"].items():
        require(sha(ROOT / name) == expected, "FROZEN_SOURCE_CHANGED:" + name)
    for name in ("protocol", "recipes"):
        require(
            sha(ROOT / f"research/profit8/{name}.json") == frozen[name + "_sha256"],
            "FROZEN_RECIPE_CHANGED",
        )
    return frozen


def journal(path: Path, kind: str, data: dict[str, Any]) -> None:
    lines = path.read_bytes().splitlines() if path.exists() else []
    prior = "0" * 64
    for i, line in enumerate(lines):
        event = json.loads(line)
        digest = event.pop("hash")
        require(
            event["seq"] == i
            and event["previous"] == prior
            and hashlib.sha256(payload(event)).hexdigest() == digest,
            "JOURNAL_CHAIN",
        )
        prior = digest
    event = {
        "seq": len(lines),
        "previous": prior,
        "recorded_at": now(),
        "kind": kind,
        "data": data,
    }
    event["hash"] = hashlib.sha256(payload(event)).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(payload(event))
        handle.flush()
        os.fsync(handle.fileno())


def call_node(args: list[str]) -> None:
    result = subprocess.run(
        ["node", "tools/profit8_replay.cjs", *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        timeout=180,
    )
    require(
        result.returncode == 0, "NATIVE_REPLAY_ERROR:" + result.stdout + result.stderr
    )
    print(result.stdout.strip(), flush=True)


def markdown(
    result: dict[str, Any], protocol: dict[str, Any], source_commit: str
) -> str:
    rows = [
        "# PROFIT8: resultado del ciclo registrado",
        "",
        "## Alcance",
        "",
        f"Fuentes congeladas en `{source_commit}`. Cuenta inicial: 20.000 USD. Período continuo: {result['period'][0]} a {result['period'][1]}, {result['sessions']} sesiones. Sin retiros ni reinicios.",
        "",
        "Son resultados históricos con ejecución modelada sobre barras SIP de cinco minutos. No acreditan rentabilidad real, ejecución de broker ni una calificación de 8/10. El histórico principal ya se había examinado. La extensión reciente quedó bloqueada por indisponibilidad de Alpaca; no se midió ningún tramo nuevo.",
        "",
        "## Todos los resultados",
        "",
        "| Política | Neto nominal USD | Neto estrés USD | Campañas nominal/estrés | Decisión |",
        "|---|---:|---:|---:|---|",
    ]
    for rid in protocol["candidates"] + protocol["controls"]:
        a, b = result["accounts"]["NOMINAL:" + rid], result["accounts"]["STRESS:" + rid]
        decision = result["decisions"].get(rid, {}).get("decision", "CONTROL")
        rows.append(
            f"| {rid} | {a['net_usd']:.2f} | {b['net_usd']:.2f} | {a['closed_campaigns']}/{b['closed_campaigns']} | {decision} |"
        )
    rows += [
        "",
        "## Interpretación registrada",
        "",
        "H1 prueba reversión de residuos negativos frente a continuación positiva. H2 predice el pago neto de la política real de stops y parciales, frente a predecir sólo el precio al deadline. H3 conserva exactamente las previsiones de H2 y enumera tamaños enteros bajo incertidumbre. Su efecto incluye cambios posteriores en inventario y admisión: no es una atribución pura sobre entradas idénticas.",
        "",
        "El motor conserva un límite común IOC causal de 30 puntos básicos, exposición bruta de 12%, riesgo agregado abierto de 0,25%, límite diario de 2% y drawdown de 8%. Estos son límites del modelo; no garantizan cotizaciones ejecutables ni ausencia de gaps en vivo.",
        "",
        "Los gastos fijos son 1 USD por fecha natural en nominal y 2 USD bajo estrés, incluidos fines de semana y calentamiento sin operaciones. Se cobran una sola vez por cuenta. Comisiones, spread y slippage figuran por separado en results.json.",
        "",
        "Los intervalos de bootstrap usan bloques de 5 y 20 sesiones y corrección local de 48 extremos registrados. La búsqueda histórica global es incompleta y no existe validación prospectiva. Los remuestreos no crean sesiones originales nuevas.",
        "",
        "## Reproducción",
        "",
        "```bash",
        "PYTHONPATH=quant:tools python tools/verify_profit8.py --directory evidence/profit8/run_01 --output /tmp/profit8-audit.json",
        "```",
        "",
        "Para repetir la matriz completa, usar run_profit8.py --mode run con un directorio nuevo y el mismo --source-commit. Una reproducción exacta debe declararse como tal y conservar los hashes; no habilita otra búsqueda de parámetros.",
        "",
        "## Presupuesto y parada",
        "",
        "Se registraron seis candidatos y cuatro controles en dos escenarios. La matriz utiliza 20 cuentas nuevas: 85 evaluaciones documentadas acumuladas. Se conservan 20 reservas sin utilizar para la extensión bloqueada, con reserva total de 105/128. Se conservan también los rechazos del ciclo anterior. El historial global de intentos sigue incompleto.",
        "",
        "No se ejecutan órdenes ni se despliega esta investigación. Una receta con resultado positivo sólo puede clasificarse como candidata diagnóstica si supera todos los filtros; la rentabilidad de producción requiere evidencia posterior y conciliación de ejecuciones reales.",
        "",
    ]
    return "\n".join(rows)


def run(directory: Path, source_commit: str) -> dict[str, Any]:
    from harpoon_quant.profit8.model import forecast_rows

    started = time.perf_counter()
    require(
        re.fullmatch(r"[0-9a-f]{40}", source_commit) is not None,
        "SOURCE_COMMIT_SHA_REQUIRED",
    )
    frozen = verify_freeze()
    protocol = read(ROOT / "research/profit8/protocol.json")
    recipes = read(ROOT / "research/profit8/recipes.json")
    require(
        not directory.exists() or not any(directory.iterdir()),
        "FRESH_RUN_DIRECTORY_REQUIRED",
    )
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("protocol", "recipes"):
        (directory / (name + ".json")).write_bytes(
            (ROOT / f"research/profit8/{name}.json").read_bytes()
        )
    data_audit_path = ROOT / protocol.get(
        "data_audit", "evidence/profit8/data/data_audit.json"
    )
    data_audit = read(data_audit_path)
    require(data_audit.get("verified") is True, "ADMITTED_DATA_AUDIT_REQUIRED")
    captures = [
        read(p)["captured_at"]
        for p in sorted((ROOT / "evidence/profit8/raw").rglob("*.json"))
    ]
    if protocol.get("data_mode") == "RETAINED_EXISTING":
        require(
            protocol["amendment"]["before_any_new_economic_measurement"] is True,
            "EXPLICIT_PRE_MEASUREMENT_AMENDMENT_REQUIRED",
        )
        require(
            protocol["dataset"] == protocol["base_dataset"]
            and sha(ROOT / protocol["dataset"]) == protocol["base_dataset_sha256"]
            and data_audit["dataset_sha256"] == protocol["base_dataset_sha256"],
            "RETAINED_DATA_IDENTITY_REQUIRED",
        )
        require(
            protocol["data_admission"]["extension_status"]
            == "BLOCKED_PROVIDER_TIMEOUT",
            "EXTENSION_STATUS_MUST_REMAIN_BLOCKED",
        )
    else:
        require(
            len(captures) >= 5
            and min(datetime.fromisoformat(c) for c in captures)
            > datetime.fromisoformat(frozen["frozen_at"]),
            "CAPTURE_MUST_FOLLOW_SOURCE_FREEZE",
        )
    data_paths = [
        ROOT / protocol["dataset"],
        ROOT / protocol["base_dataset"],
        data_audit_path,
        *sorted((ROOT / "evidence/profit8/raw").rglob("*.json")),
    ]
    bindings = {
        "schema": "HARPOON_PROFIT8_BINDINGS_1",
        "sources": frozen["sources"],
        "data": {str(p.relative_to(ROOT)): sha(p) for p in data_paths},
        "protocol_sha256": frozen["protocol_sha256"],
        "recipes_sha256": frozen["recipes_sha256"],
        "source_commit": source_commit,
        "source_freeze_sha256": sha(
            ROOT / protocol.get("source_freeze", "research/profit8/source_freeze.json")
        ),
    }
    write(directory / "source_bindings.json", bindings)
    log = directory / "journal.jsonl"
    journal(
        log,
        "RESERVE_BEFORE_MEASUREMENT",
        {
            "source_commit": source_commit,
            "bindings_sha256": sha(directory / "source_bindings.json"),
            "budget": protocol["budget"],
        },
    )
    data = read(ROOT / protocol["dataset"])
    prepared = build_rows(data, protocol)
    write(directory / "teacher_signals.json", prepared.pop("teacher_signals"))
    teachers = {}
    with tempfile.TemporaryDirectory(prefix="harpoon-profit8-") as temporary:
        temp = Path(temporary)
        for scenario in protocol["scenarios"]:
            path = temp / ("teachers_" + scenario + ".json")
            call_node(
                [
                    "teacher",
                    "--protocol",
                    str(directory / "protocol.json"),
                    "--signals",
                    str(directory / "teacher_signals.json"),
                    "--scenario",
                    scenario,
                    "--output",
                    str(path),
                ]
            )
            teachers[scenario] = read(path)
            write(
                directory / ("teachers_" + scenario + ".json.gz"),
                teachers[scenario],
                compressed=True,
            )
        attach_teachers(prepared["rows"], teachers)
        write(directory / "rows.json.gz", prepared, compressed=True)
        forecasts = forecast_rows(prepared["rows"], protocol)
        write(directory / "forecasts.json.gz", forecasts, compressed=True)
        bundle = make_bundle(prepared["rows"], forecasts, protocol, recipes)
        write(directory / "signals.json", bundle)
        print(
            json.dumps(
                {
                    "rows": len(prepared["rows"]),
                    "signals": {
                        s: {r: len(v) for r, v in x.items()}
                        for s, x in bundle["signals"].items()
                    },
                    "forecast_diagnostics": forecasts.get("diagnostics", {}),
                }
            ),
            flush=True,
        )
        reports = {}
        for scenario in protocol["scenarios"]:
            for recipe in recipes:
                rid = recipe["id"]
                key = scenario + ":" + rid
                journal(log, "ACCOUNT_MEASUREMENT_STARTED", {"key": key})
                path = temp / (scenario + "_" + rid + ".json")
                call_node(
                    [
                        "replay",
                        "--protocol",
                        str(directory / "protocol.json"),
                        "--bundle",
                        str(directory / "signals.json"),
                        "--recipe",
                        rid,
                        "--scenario",
                        scenario,
                        "--output",
                        str(path),
                    ]
                )
                report = read(path)
                reports[key] = report
                output = directory / (scenario + "_" + rid + ".json.gz")
                write(output, report, compressed=True)
                journal(
                    log,
                    "ACCOUNT_MEASUREMENT_COMPLETED",
                    {"key": key, "sha256": sha(output)},
                )
    result = statistics(reports, protocol)
    write(directory / "results.json", result)
    require(not (directory / "report.md").exists(), "IMMUTABLE_REPORT")
    (directory / "report.md").write_text(markdown(result, protocol, source_commit))
    verify_freeze()
    journal(
        log,
        "MATRIX_COMPLETED",
        {
            "accounts": len(reports),
            "results_sha256": sha(directory / "results.json"),
            "stopping_rule": "NO_RECIPE_RETUNING",
            "budget_reserved_after": 105,
        },
    )
    audit = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/verify_profit8.py"),
            "--directory",
            str(directory),
            "--output",
            str(directory / "audit.json"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    print(audit.stdout, flush=True)
    require(
        audit.returncode == 0,
        "INDEPENDENT_ACCOUNT_AUDIT_FAILED:" + audit.stdout + audit.stderr,
    )
    runtime = {
        "schema": "HARPOON_PROFIT8_RUN_RECEIPT_1",
        "source_commit": source_commit,
        "source_freeze_sha256": sha(
            ROOT / protocol.get("source_freeze", "research/profit8/source_freeze.json")
        ),
        "started_after_source_freeze": True,
        "finished_at": now(),
        "wall_seconds": time.perf_counter() - started,
        "python": sys.version,
        "platform": platform.platform(),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "financial_acceptance_allowed": False,
        "live_approved": False,
    }
    write(directory / "run_receipt.json", runtime)
    write(
        directory / "manifest.json",
        {
            "schema": "HARPOON_PROFIT8_OUTPUT_MANIFEST_1",
            "files": {
                p.name: sha(p) for p in sorted(directory.iterdir()) if p.is_file()
            },
        },
    )
    return {
        "directory": str(directory),
        "decisions": result["decisions"],
        "wall_seconds": runtime["wall_seconds"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("freeze", "run"), required=True)
    parser.add_argument(
        "--directory", type=Path, default=ROOT / "evidence/profit8/run_01"
    )
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    if args.mode == "freeze":
        result = freeze()
        print(
            json.dumps(
                {
                    "frozen_at": result["frozen_at"],
                    "sources": len(result["sources"]),
                    "economic_measurements_executed": False,
                }
            )
        )
    else:
        require(args.source_commit is not None, "SOURCE_COMMIT_REQUIRED")
        print(json.dumps(run(args.directory.resolve(), args.source_commit)))


if __name__ == "__main__":
    main()
