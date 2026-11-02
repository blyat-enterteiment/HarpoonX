"""XXXUltimate PAPER installer; stdlib only, no broker API or shell evaluation.

Dry checks never invoke Docker. Credentials travel only in the child environment,
not argv, generated files or installer output. Docker retains its normal runtime
environment metadata. Legacy mode requires an explicitly existing compose.json;
the old configure.py is preserved and is never invoked automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn, Protocol, TextIO
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "harpoon-xxxultimate"
SERVICE = "xxxultimate"
REQUIRED = ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "HARPOON_PANEL_PASSWORD")
RUNTIME_KEYS = (
    *REQUIRED, "HARPOON_START_PAPER", "HARPOON_PUBLIC_ORIGIN", "HARPOON_EXPECTED_ACCOUNT_ID",
    "HARPOON_STORAGE_TIMEOUT_MS",
    "HARPOON_QUANT_MODEL", "IRONBEAM_USERNAME", "IRONBEAM_PASSWORD", "IRONBEAM_API_KEY",
    "IRONBEAM_ACCOUNT_ID", "HARPOON_FUTURES_CONTRACTS", "HARPOON_FUTURES_PAPER_ORDERS",
    "IRONBEAM_COMMISSION_PER_SIDE_USD",
)
HOST_KEYS = (
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
    "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
    "SSH_AUTH_SOCK", "XDG_RUNTIME_DIR", "SYSTEMROOT", "WINDIR",
)
STOP_NOTICE = (
    "Detener el runtime interrumpe la protección y las salidas gestionadas por software. "
    "Las órdenes aceptadas siguen en el broker. No se envían cancelaciones ni cierres."
)


class InstallError(Exception):
    """Code-only errors: no secret value or subprocess diagnostic."""

    def __init__(self, code: str, *, fields: Sequence[str] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.fields = list(fields)


def error(code: str, *fields: str) -> NoReturn:
    raise InstallError(code, fields=fields)


def parse_env(text: str) -> dict[str, str]:
    """Literal KEY=value, optional export/quotes; never expand dollar or commands."""
    if len(text.encode("utf-8")) > 262144:
        error("ENV_FILE_TOO_LARGE")
    values: dict[str, str] = {}
    for number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            error("ENV_ASSIGNMENT_INVALID", f"line:{number}")
        if key in values:
            error("ENV_DUPLICATE_KEY", f"line:{number}")
        if value[:1] in {"'", '"'}:
            quote, pieces, i, closed = value[0], [], 1, False
            while i < len(value):
                char = value[i]
                if char == quote:
                    tail = value[i + 1:].strip()
                    if tail and not tail.startswith("#"):
                        error("ENV_TRAILING_TEXT", f"line:{number}")
                    closed = True
                    break
                if char == "\\" and i + 1 < len(value) and value[i + 1] in {quote, "\\"}:
                    i += 1
                    char = value[i]
                pieces.append(char)
                i += 1
            if not closed:
                error("ENV_QUOTE_UNCLOSED", f"line:{number}")
            value = "".join(pieces)
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            error("ENV_CONTROL_CHARACTER", f"line:{number}")
        values[key] = value
    return values


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            error("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _finite_json(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        error("JSON_NONFINITE_NUMBER")
    if isinstance(value, dict):
        for child in value.values():
            _finite_json(child)
    if isinstance(value, list):
        for child in value:
            _finite_json(child)


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        if not path.is_file() or path.stat().st_size > 4194304:
            error("CONFIG_FILE_MISSING_OR_TOO_LARGE")
        raw = path.read_bytes()
        data = json.loads(raw, object_pairs_hook=_pairs)
        if not isinstance(data, dict):
            error("CONFIG_OBJECT_REQUIRED")
        _finite_json(data)
        return data, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise InstallError("CONFIG_READ_OR_JSON_INVALID") from None


def _path(root: Path, value: str) -> Path:
    if not value or any(char in value for char in "\0\n\r"):
        error("PATH_INVALID")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def _origin(value: str, bind: str, port: int) -> str:
    origin = value or f"http://127.0.0.1:{port}"
    try:
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment or parsed.port == 0):
            error("PUBLIC_ORIGIN_INVALID")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            error("HTTPS_ORIGIN_REQUIRED_OUTSIDE_LOCALHOST")
        if not ipaddress.ip_address(bind).is_loopback and (not value or parsed.scheme != "https"):
            error("EXPLICIT_HTTPS_ORIGIN_REQUIRED_FOR_NONLOCAL_BIND")
    except ValueError:
        raise InstallError("PUBLIC_ORIGIN_INVALID") from None
    return origin


@dataclass(frozen=True)
class Settings:
    root: Path
    action: str
    legacy: bool
    compose_file: Path
    project: str
    config_file: Path | None
    data_path: Path | None
    config_sha256: str | None
    compose_sha256: str
    bind_host: str
    host_port: int
    child_env: dict[str, str] = field(repr=False)

    def compose(self, *args: str) -> list[str]:
        return ["docker", "compose", "--env-file", os.devnull, "--project-directory", str(self.root),
                "--project-name", self.project, "-f", str(self.compose_file), *args]

    def commands(self) -> list[list[str]]:
        if self.action == "status":
            return [self.compose("ps", "--all", "--format", "json")]
        if self.action == "stop":
            return [self.compose("stop", *([] if self.legacy else [SERVICE]))]
        services = [] if self.legacy else [SERVICE]
        up = ["up", "-d", "--no-build"]
        if not self.legacy:
            up.extend(["--scale", f"{SERVICE}=1", SERVICE])
        return [self.compose("config", "--quiet"), self.compose("build", *services), self.compose(*up)]

    def public(self) -> dict[str, Any]:
        return {
            "schema": "HARPOON_INSTALL_PLAN_1", "mode": "LEGACY_EXPLICIT" if self.legacy else "XXXULTIMATE",
            "action": self.action, "status": "LOCAL_VALIDATION_PASSED", "planned_only": True,
            "project": self.project, "compose_file": str(self.compose_file),
            "configuration": None if self.config_file is None else {"source": str(self.config_file),
                "target": "/run/harpoon/config.json", "read_only": True, "sha256": self.config_sha256},
            "persistent_data": None if self.data_path is None else {"source": str(self.data_path), "target": "/var/data"},
            "host_bind": None if self.legacy else {"address": self.bind_host, "port": self.host_port},
            "environment_names": sorted(key for key in RUNTIME_KEYS if self.child_env.get(key)),
            "commands": self.commands(), "secret_values_in_plan": False,
            "docker_schema_build_and_runtime_verified": False, "broker_account_verified": False,
            "account_binding": "PENDING_RUNTIME_AND_EXISTING_JOURNAL_CHECKS",
            "persisted_pause": "PRESERVED_BY_RUNTIME_JOURNAL; START_PAPER_DOES_NOT_CLEAR_IT",
            "financial_authorization": False, "runtime_readiness_verified": False,
            "stop_notice": STOP_NOTICE if self.action == "stop" else None,
        }


def settings(root: Path, action: str, *, legacy: bool = False, env_file: Path | None = None,
             environment: Mapping[str, str] | None = None) -> Settings:
    root = root.resolve()
    inherited = dict(os.environ if environment is None else environment)
    source = env_file if env_file is not None else root / ".env"
    if not source.is_absolute():
        source = root / source
    supplied: dict[str, str] = {}
    try:
        if source.exists():
            supplied = parse_env(source.read_text(encoding="utf-8"))
        elif env_file is not None:
            error("ENV_FILE_NOT_FOUND")
    except (OSError, UnicodeError):
        raise InstallError("ENV_FILE_READ_FAILED") from None
    values = {**supplied, **inherited}  # Process env wins; no dotenv expansion.
    child = {key: inherited[key] for key in HOST_KEYS if inherited.get(key)}
    child["COMPOSE_DISABLE_ENV_FILE"] = "true"
    if legacy:
        compose_file = root / "compose.json"
        if not compose_file.exists():
            error("LEGACY_EXISTING_COMPOSE_REQUIRED")
        config, checksum = read_json(compose_file)
        services = config.get("services")
        if not isinstance(services, dict) or not ({"equity", "crypto"} & services.keys()):
            error("LEGACY_SERVICES_REQUIRED")
        if not set(services).issubset({"equity", "crypto", "https", "backups", "gpt"}):
            error("LEGACY_SERVICE_LAYOUT_INVALID")
        project = config.get("name", "harpoon-cloud")
        if not isinstance(project, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project) or project == PROJECT:
            error("LEGACY_PROJECT_INVALID")
        return Settings(root, action, True, compose_file, project, None, None, None,
                        checksum, "", 0, child)
    compose_file = root / "deploy/compose.xxx.json"
    compose_data, compose_hash = read_json(compose_file)
    if set(compose_data.get("services", {})) != {SERVICE}:
        error("ULTIMATE_SINGLE_COORDINATOR_REQUIRED")
    config_file = _path(root, values.get("HARPOON_CONFIG", "config/examples/xxx.json"))
    data_path = _path(root, values.get("HARPOON_DATA", "data/xxx"))
    if config_file.is_relative_to(data_path) or root.is_relative_to(data_path):
        error("CONFIG_OR_SOURCE_INSIDE_WRITABLE_DATA")
    if data_path.exists() and not data_path.is_dir():
        error("DATA_PATH_NOT_DIRECTORY")
    if data_path.is_relative_to(root) and data_path.relative_to(root).parts[0] in {
        "xxx", "src", "runtime", "runtime30", "deploy", "config", "quant", "tools", "node_modules", ".git",
    }:
        error("DATA_PATH_IS_SOURCE_DIRECTORY")
    config_hash: str | None = None
    if action == "install":
        config, config_hash = read_json(config_file)
        if config.get("mode") != "paper" or config.get("execution_authority") != "dedicated_remote_account":
            error("DEDICATED_PAPER_CONFIGURATION_REQUIRED")
        if not isinstance(config.get("expected_account_id", ""), str):
            error("ACCOUNT_ID_TYPE_INVALID")
        if not isinstance(config.get("universe"), list) or not config["universe"] or not isinstance(config.get("exit"), dict):
            error("XXX_UNIVERSE_AND_EXIT_REQUIRED")
        missing = [key for key in REQUIRED if not values.get(key)]
        if missing:
            error("REQUIRED_ENVIRONMENT_MISSING", *missing)
        if len(values["HARPOON_PANEL_PASSWORD"]) < 32:
            error("PANEL_PASSWORD_MINIMUM_32_CHARACTERS")
        for key in RUNTIME_KEYS:
            value = values.get(key, "")
            if len(value) > 65536 or any(ord(char) < 32 or ord(char) == 127 for char in value):
                error("RUNTIME_ENVIRONMENT_VALUE_INVALID", key)
        if any(values.get(key + "_FILE") for key in REQUIRED):
            error("HOST_SECRET_FILE_NOT_MOUNTED_USE_ENVIRONMENT")
        info = config_file.stat()
        if os.name == "posix" and not (info.st_mode & stat.S_IROTH
                or (info.st_uid == 1000 and info.st_mode & stat.S_IRUSR)
                or (info.st_gid == 1000 and info.st_mode & stat.S_IRGRP)):
            error("CONFIG_MUST_BE_READABLE_BY_CONTAINER_UID_1000")
        parent = data_path
        while not parent.exists():
            parent = parent.parent
        if not data_path.exists() and not os.access(parent, os.W_OK | os.X_OK):
            error("DATA_PARENT_NOT_WRITABLE")
        if not (root / "deploy/Dockerfile.xxx").is_file():
            error("ULTIMATE_DOCKERFILE_MISSING")
    try:
        bind = str(ipaddress.ip_address(values.get("BIND_HOST", "127.0.0.1")))
        port_text = values.get("PORT", "10000")
        if not re.fullmatch(r"[0-9]{1,5}", port_text) or not 1 <= int(port_text) <= 65535:
            error("PORT_INVALID")
        port = int(port_text)
    except ValueError:
        raise InstallError("BIND_ADDRESS_INVALID") from None
    origin = _origin(values.get("HARPOON_PUBLIC_ORIGIN", ""), bind, port)
    for key, default in (("HARPOON_START_PAPER", "1"), ("HARPOON_FUTURES_PAPER_ORDERS", "0")):
        if values.get(key, default) not in {"0", "1"}:
            error("PAPER_SWITCH_INVALID", key)
        child[key] = values.get(key, default)
    storage_timeout = values.get("HARPOON_STORAGE_TIMEOUT_MS", "2000")
    if not re.fullmatch(r"[0-9]{2,4}", storage_timeout) or not 50 <= int(storage_timeout) <= 5000:
        error("STORAGE_TIMEOUT_INVALID", "HARPOON_STORAGE_TIMEOUT_MS")
    for key in RUNTIME_KEYS:
        if values.get(key):
            child[key] = values[key]
    child.update(HARPOON_STORAGE_TIMEOUT_MS=str(int(storage_timeout)),
                 HARPOON_PUBLIC_ORIGIN=origin, HX_APP_ROOT=str(root), HX_DATA_PATH=str(data_path),
                 HX_CONFIG_PATH=str(config_file), HX_BIND_HOST=bind, HX_HOST_PORT=str(port))
    return Settings(root, action, False, compose_file, PROJECT, config_file, data_path,
                    config_hash, compose_hash, bind, port, child)


class Runner(Protocol):
    def __call__(self, args: Sequence[str], *, cwd: Path, env: Mapping[str, str], timeout: int) -> subprocess.CompletedProcess[str]: ...


def run_process(args: Sequence[str], *, cwd: Path, env: Mapping[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=cwd, env=dict(env), timeout=timeout, check=False,
                          text=True, capture_output=True, shell=False)


def _run(plan: Settings, args: Sequence[str], stage: str, runner: Runner, timeout: int = 60) -> str:
    try:
        result = runner(args, cwd=plan.root, env=plan.child_env, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise InstallError("COMMAND_UNAVAILABLE_OR_TIMEOUT", fields=[stage]) from None
    if result.returncode:
        error("COMMAND_FAILED", stage, f"exit:{result.returncode}")
    return result.stdout  # Callers never relay arbitrary stdout/stderr.


def _records(raw: str) -> list[dict[str, Any]]:
    if len(raw.encode("utf-8")) > 2097152:
        error("DOCKER_STATUS_OUTPUT_BOUND")
    if not raw.strip():
        return []
    try:
        values = json.loads(raw) if raw.lstrip().startswith("[") else [json.loads(line) for line in raw.splitlines() if line.strip()]
        if not isinstance(values, list) or not all(isinstance(row, dict) for row in values):
            error("DOCKER_STATUS_FORMAT_INVALID")
        return values
    except json.JSONDecodeError:
        raise InstallError("DOCKER_STATUS_FORMAT_INVALID") from None


def _conflicts(plan: Settings, runner: Runner) -> None:
    raw = _run(plan, ["docker", "ps", "--format", "{{json .}}"], "CONFLICT_CHECK", runner)
    for row in _records(raw):
        labels = row.get("Labels", "")
        if not isinstance(labels, str):
            error("DOCKER_LABELS_FORMAT_INVALID")
        mapping = dict(part.split("=", 1) for part in labels.split(",") if "=" in part)
        service = mapping.get("com.docker.compose.service", "")
        project = mapping.get("com.docker.compose.project", "")
        is_ultimate = service == SERVICE or row.get("Names") == PROJECT or mapping.get("io.harpoon.runtime") == "XXXUltimate"
        is_legacy = service in {"equity", "crypto"}
        if (plan.legacy and is_ultimate) or (not plan.legacy and is_legacy):
            error("OTHER_HARPOON_RUNTIME_ACTIVE_STOP_EXPLICITLY_FIRST")
        if ((is_legacy and plan.legacy) or (is_ultimate and not plan.legacy)) and project != plan.project:
            error("ANOTHER_HARPOON_PROJECT_ACTIVE")


def execute(plan: Settings, *, runner: Runner = run_process, output: TextIO = sys.stdout) -> dict[str, Any]:
    version = _run(plan, ["docker", "compose", "version", "--short"], "COMPOSE_VERSION", runner)
    match = re.match(r"v?(\d+)\.", version.strip())
    if not match or int(match.group(1)) < 2:
        error("DOCKER_COMPOSE_V2_REQUIRED")
    commands = plan.commands()
    if plan.action == "install":
        _conflicts(plan, runner)
        _run(plan, commands[0], "COMPOSE_CONFIG", runner)
        print("Construyendo el runtime seleccionado; no se muestran valores de entorno.", file=output, flush=True)
        _run(plan, commands[1], "BUILD", runner, 1800)
        _conflicts(plan, runner)
        if read_json(plan.compose_file)[1] != plan.compose_sha256:
            error("COMPOSE_CHANGED_DURING_BUILD")
        if plan.config_file is not None and read_json(plan.config_file)[1] != plan.config_sha256:
            error("CONFIG_CHANGED_DURING_BUILD")
        if plan.data_path is not None:
            if plan.data_path.resolve() != plan.data_path or plan.config_file is None or plan.config_file.resolve() != plan.config_file:
                error("BIND_PATH_CHANGED_DURING_BUILD")
            plan.data_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        _run(plan, commands[2], "UP", runner, 180)
        return {"status": "START_REQUESTED", "mode": "LEGACY_EXPLICIT" if plan.legacy else "XXXULTIMATE",
                "project": plan.project, "broker_account_verified": False, "runtime_readiness_verified": False,
                "financial_authorization": False, "next": "Consultar status.sh y el endpoint operacional autenticado."}
    if plan.action == "stop":
        print(STOP_NOTICE, file=output, flush=True)
        _run(plan, commands[0], "STOP", runner, 180)
        return {"status": "STOP_REQUEST_COMPLETED", "project": plan.project, "journal_deleted": False,
                "broker_orders_sent": False, "protection_interrupted": True}
    rows = _records(_run(plan, commands[0], "STATUS", runner))
    states = []
    for row in rows:
        service, state, health = row.get("Service"), row.get("State"), row.get("Health", "")
        allowed = {"equity", "crypto", "https", "backups", "gpt"} if plan.legacy else {SERVICE}
        if not isinstance(service, str) or service not in allowed:
            error("DOCKER_STATUS_SERVICE_INVALID")
        if not isinstance(state, str) or state not in {"running", "created", "restarting", "paused", "exited", "dead", "removing"}:
            error("DOCKER_STATUS_STATE_INVALID")
        states.append({"service": service, "state": state, "health": health if isinstance(health, str) and health in {"", "starting", "healthy", "unhealthy"} else "unknown"})
    return {"status": "CONTAINER_STATUS_ONLY", "project": plan.project, "containers": states,
            "health_meaning": "HTTP_ALIVE_ONLY", "broker_orders_sent": False, "runtime_readiness_verified": False}


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT, environment: Mapping[str, str] | None = None,
         runner: Runner = run_process, output: TextIO = sys.stdout, errors: TextIO = sys.stderr) -> int:
    parser = argparse.ArgumentParser(description="Instalador XXXUltimate PAPER; --check/--plan son locales y no invocan Docker.")
    parser.add_argument("action", choices=("install", "status", "stop"))
    parser.add_argument("--legacy", action="store_true", help="Operar únicamente el compose.json legacy ya existente.")
    parser.add_argument("--env-file", type=Path, help="Archivo literal KEY=value; nunca se ejecuta.")
    dry = parser.add_mutually_exclusive_group()
    dry.add_argument("--check", action="store_true", help="Validar entorno local sin construir ni iniciar.")
    dry.add_argument("--plan", action="store_true", help="Mostrar argumentos y rutas sin valores secretos ni ejecución.")
    args = parser.parse_args(argv)
    try:
        plan = settings(root, args.action, legacy=args.legacy, env_file=args.env_file, environment=environment)
        result = plan.public() if args.check or args.plan else execute(plan, runner=runner, output=output)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=output)
        return 0
    except InstallError as exc:
        print(json.dumps({"status": "BLOCKED", "code": exc.code, "fields": exc.fields,
                          "scope": "INSTALLER_VALIDATION_OR_DOCKER_COMMAND; NO_BROKER_VERIFICATION",
                          "secret_values_in_output": False}, ensure_ascii=False), file=errors)
        return 2
    except (OSError, ValueError):
        print('{"status":"BLOCKED","code":"LOCAL_IO_OR_CONFIGURATION_ERROR","secret_values_in_output":false}', file=errors)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
