"""Offline installer contract tests. Docker and broker endpoints are never used."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ultimate_install_under_test", APP / "deploy/ultimate_install.py")
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)
KEY = "SYNTHETIC_PAPER_KEY_NOT_A_REAL_CREDENTIAL"
SECRET = "SYNTHETIC_SECRET_NEVER_DISPLAYED_$(not_executed)"
PASSWORD = "SYNTHETIC_PANEL_PASSWORD_32_PLUS_CHARACTERS"


class FakeDocker:
    def __init__(self):
        self.calls = []
        self.containers = []
        self.status = []
        self.version = "2.40.3\n"
        self.fail_stage = None
        self.on_build = None

    def __call__(self, args, *, cwd, env, timeout):
        args = list(args)
        self.calls.append((args, dict(env), cwd, timeout))
        output = ""
        if args[:3] == ["docker", "compose", "version"]:
            output = self.version
        elif args[:2] == ["docker", "ps"]:
            output = "\n".join(json.dumps(r) for r in self.containers)
        elif "build" in args and self.on_build:
            self.on_build()
        elif "ps" in args:
            output = "\n".join(json.dumps(r) for r in self.status)
        failed = self.fail_stage is not None and self.fail_stage in args
        return subprocess.CompletedProcess(args, 1 if failed else 0, SECRET if failed else output, PASSWORD if failed else "")


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="harpoon-installer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "app with spaces"
        for directory in ("deploy", "config/examples"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        for name in ("deploy/compose.xxx.json", "deploy/ultimate_install.py", "deploy/Dockerfile.xxx",
                     "config/examples/xxx.json", "install.sh", "status.sh", "stop.sh"):
            shutil.copyfile(APP / name, self.root / name)
        self.config = self.root / "config/examples/xxx.json"
        self.config.chmod(0o644)
        self.env = {"APCA_API_KEY_ID": KEY, "APCA_API_SECRET_KEY": SECRET, "HARPOON_PANEL_PASSWORD": PASSWORD,
                    "PATH": os.environ.get("PATH", os.defpath)}
        self.fake = FakeDocker()

    def run_cli(self, *args, env=None):
        out, err = io.StringIO(), io.StringIO()
        code = installer.main(list(args), root=self.root, environment=self.env if env is None else env,
                              runner=self.fake, output=out, errors=err)
        text = out.getvalue() + err.getvalue()
        for secret in (KEY, SECRET, PASSWORD):
            self.assertNotIn(secret, text)
        return code, out.getvalue(), err.getvalue()

    def mutate_config(self, **changes):
        config = json.loads(self.config.read_text())
        config.update(changes)
        self.config.write_text(json.dumps(config))

    def write_legacy(self):
        path = self.root / "compose.json"
        path.write_text(json.dumps({"name": "harpoon-cloud", "services": {"equity": {}, "crypto": {}, "https": {}}}))
        return path

    def test_plan_is_local_secret_free_and_uses_only_ultimate(self):
        self.write_legacy()
        code, out, _ = self.run_cli("install", "--plan")
        self.assertEqual(code, 0)
        plan = json.loads(out)
        self.assertEqual(plan["mode"], "XXXULTIMATE")
        self.assertEqual(plan["project"], "harpoon-xxxultimate")
        self.assertFalse(plan["broker_account_verified"])
        self.assertFalse(plan["financial_authorization"])
        self.assertEqual(plan["host_bind"], {"address": "127.0.0.1", "port": 10000})
        self.assertIn("xxxultimate=1", plan["commands"][-1])
        self.assertEqual(self.fake.calls, [])
        self.assertFalse((self.root / "data").exists())

    def test_compose_has_one_runtime_ro_config_and_persistent_data(self):
        data = json.loads((self.root / "deploy/compose.xxx.json").read_text())
        self.assertEqual(list(data["services"]), ["xxxultimate"])
        service = data["services"]["xxxultimate"]
        self.assertEqual(service["build"]["dockerfile"], "deploy/Dockerfile.xxx")
        self.assertEqual(service["environment"]["HARPOON_DATA"], "/var/data")
        self.assertEqual(service["environment"]["HARPOON_CONFIG"], "/run/harpoon/config.json")
        self.assertEqual(service["environment"]["BIND_HOST"], "0.0.0.0")
        self.assertEqual(service["environment"]["PORT"], "10000")
        self.assertNotIn("HARPOON_QUANT_PYTHON", service["environment"])
        volumes = {v["target"]: v for v in service["volumes"]}
        self.assertTrue(volumes["/run/harpoon/config.json"]["read_only"])
        self.assertFalse(volumes["/var/data"]["read_only"])
        self.assertEqual(service["stop_grace_period"], "60s")

    def test_env_is_literal_data_not_shell_or_interpolation(self):
        marker = Path(self.temp.name) / "must_not_exist"
        value = f"$(touch {marker})`touch {marker}`${{HOME}}"
        source = "export APCA_API_KEY_ID='" + value + "'\nAPCA_API_SECRET_KEY=plain#literal\nHARPOON_PANEL_PASSWORD='" + PASSWORD + "' # comment\n"
        (self.root / ".env").write_text(source)
        plan = installer.settings(self.root, "install", environment={})
        self.assertEqual(plan.child_env["APCA_API_KEY_ID"], value)
        self.assertEqual(plan.child_env["APCA_API_SECRET_KEY"], "plain#literal")
        self.assertFalse(marker.exists())
        self.assertNotIn(value, json.dumps(plan.public()))

    def test_bash_wrapper_plan_executes_only_python_from_arbitrary_directory(self):
        (self.root / ".env").write_text("\n".join(f"{k}='{v}'" for k, v in self.env.items() if k != "PATH"))
        result = subprocess.run(["bash", str(self.root / "install.sh"), "--plan"],
                                cwd=self.temp.name, env={"PATH": os.environ.get("PATH", os.defpath)},
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "XXXULTIMATE")
        for secret in (KEY, SECRET, PASSWORD):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_invalid_dotenv_syntax_and_duplicates_do_not_execute(self):
        for text in ("A=x\nA=y", "touch /tmp/not_run", "A='unclosed", "A='x' junk", "A=bad\x00value"):
            with self.subTest(text_type=text[:1]), self.assertRaises(installer.InstallError):
                installer.parse_env(text)

    def test_environment_override_and_host_interpreters_are_not_forwarded(self):
        (self.root / ".env").write_text("HARPOON_START_PAPER=0\nHARPOON_QUANT_PYTHON=python3\nPYTHON=/host/only\nCOMPOSE_FILE=evil.yml\nBASH_ENV=evil.sh\n")
        plan = installer.settings(self.root, "install", environment=self.env)
        self.assertEqual(plan.child_env["HARPOON_START_PAPER"], "0")
        for key in ("HARPOON_QUANT_PYTHON", "PYTHON", "COMPOSE_FILE", "BASH_ENV"):
            self.assertNotIn(key, plan.child_env)
        changed = installer.settings(self.root, "install", environment={**self.env, "HARPOON_START_PAPER": "1"})
        self.assertEqual(changed.child_env["HARPOON_START_PAPER"], "1")

    def test_storage_timeout_default_boundaries_and_local_checks(self):
        service = json.loads((self.root / "deploy/compose.xxx.json").read_text())["services"]["xxxultimate"]
        self.assertIn("HARPOON_STORAGE_TIMEOUT_MS", service["environment"])
        self.assertIsNone(service["environment"]["HARPOON_STORAGE_TIMEOUT_MS"])
        for supplied, expected in ((None, "2000"), ("50", "50"), ("2500", "2500"), ("5000", "5000")):
            env = dict(self.env)
            if supplied is not None:
                env["HARPOON_STORAGE_TIMEOUT_MS"] = supplied
            with self.subTest(timeout=supplied):
                plan = installer.settings(self.root, "install", environment=env)
                self.assertEqual(plan.child_env["HARPOON_STORAGE_TIMEOUT_MS"], expected)
                for option in ("--check", "--plan"):
                    code, out, _ = self.run_cli("install", option, env=env)
                    self.assertEqual(code, 0)
                    self.assertIn("HARPOON_STORAGE_TIMEOUT_MS", json.loads(out)["environment_names"])
                self.assertEqual(self.fake.calls, [])

    def test_storage_timeout_environment_overrides_file_and_reaches_install_commands(self):
        (self.root / ".env").write_text("HARPOON_STORAGE_TIMEOUT_MS=1500\n")
        file_plan = installer.settings(self.root, "install", environment=self.env)
        self.assertEqual(file_plan.child_env["HARPOON_STORAGE_TIMEOUT_MS"], "1500")
        code, _, _ = self.run_cli("install", env={**self.env, "HARPOON_STORAGE_TIMEOUT_MS": "4500"})
        self.assertEqual(code, 0)
        self.assertTrue(self.fake.calls)
        self.assertTrue(all(call[1]["HARPOON_STORAGE_TIMEOUT_MS"] == "4500" for call in self.fake.calls))

    def test_invalid_storage_timeout_stops_before_docker_for_install_check_and_plan(self):
        for value in ("", "0", "49", "5001", "10000", "-1", "2000.5", "2e3", "NaN", "Infinity", "bad"):
            for options in ((), ("--check",), ("--plan",)):
                with self.subTest(timeout=value, options=options):
                    code, _, err = self.run_cli("install", *options, env={**self.env, "HARPOON_STORAGE_TIMEOUT_MS": value})
                    self.assertEqual(code, 2)
                    self.assertEqual(json.loads(err)["code"], "STORAGE_TIMEOUT_INVALID")
                    self.assertEqual(self.fake.calls, [])

    def test_missing_credentials_stop_before_any_command(self):
        code, _, err = self.run_cli("install", env={})
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "REQUIRED_ENVIRONMENT_MISSING")
        self.assertEqual(self.fake.calls, [])

    def test_paper_auth_and_switch_validation_precede_docker(self):
        cases = ({"HARPOON_PANEL_PASSWORD": "short"}, {"HARPOON_START_PAPER": "true"},
                 {"HARPOON_FUTURES_PAPER_ORDERS": "live"}, {"APCA_API_SECRET_KEY": "bad\nvalue"})
        for change in cases:
            with self.subTest(fields=list(change)):
                code, _, _ = self.run_cli("install", env={**self.env, **change})
                self.assertEqual(code, 2)
                self.assertEqual(self.fake.calls, [])
        self.mutate_config(mode="live")
        self.assertEqual(self.run_cli("install")[0], 2)
        self.assertEqual(self.fake.calls, [])

    def test_empty_account_identity_is_preserved_for_runtime_binding(self):
        self.mutate_config(expected_account_id="")
        original = self.config.read_bytes()
        code, out, _ = self.run_cli("install", "--check")
        self.assertEqual(code, 0)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(json.loads(out)["account_binding"], "PENDING_RUNTIME_AND_EXISTING_JOURNAL_CHECKS")

    def test_config_cannot_be_aliased_inside_writable_data(self):
        code, _, err = self.run_cli("install", "--check", env={**self.env, "HARPOON_DATA": "config"})
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "CONFIG_OR_SOURCE_INSIDE_WRITABLE_DATA")
        self.assertEqual(self.run_cli("install", "--check", env={**self.env, "HARPOON_DATA": "."})[0], 2)

    def test_bind_origin_and_ports_are_validated(self):
        for change in ({"PORT": "0"}, {"PORT": "10000;echo bad"}, {"BIND_HOST": "0.0.0.0"},
                       {"HARPOON_PUBLIC_ORIGIN": "http://remote.example"}, {"HARPOON_PUBLIC_ORIGIN": "https://u:p@example.com"}):
            self.assertEqual(self.run_cli("install", "--plan", env={**self.env, **change})[0], 2)
        code, out, _ = self.run_cli("install", "--plan", env={**self.env, "BIND_HOST": "0.0.0.0", "PORT": "11000", "HARPOON_PUBLIC_ORIGIN": "https://example.test"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["host_bind"]["port"], 11000)

    def test_start_uses_validated_config_build_and_one_up_without_rewriting_journal(self):
        data = self.root / "data/xxx"
        data.mkdir(parents=True)
        journal = data / "xxx.sqlite"
        journal.write_bytes(b"opaque-existing-journal-with-persisted-pause")
        before_config, before_journal = self.config.read_bytes(), journal.read_bytes()
        code, _, _ = self.run_cli("install", env={**self.env, "HARPOON_START_PAPER": "0"})
        self.assertEqual(code, 0)
        commands = [x[0] for x in self.fake.calls]
        self.assertEqual(sum("build" in c for c in commands), 1)
        self.assertEqual(sum("up" in c for c in commands), 1)
        self.assertEqual(commands[-1][-6:], ["up", "-d", "--no-build", "--scale", "xxxultimate=1", "xxxultimate"])
        self.assertIn(["config", "--quiet"], [c[-2:] for c in commands])
        self.assertTrue(all(x[1]["HARPOON_START_PAPER"] == "0" for x in self.fake.calls))
        self.assertEqual(self.config.read_bytes(), before_config)
        self.assertEqual(journal.read_bytes(), before_journal)
        self.assertFalse((self.root / "secrets").exists())

    def test_legacy_conflict_blocks_before_build(self):
        self.fake.containers = [{"Names": "legacy", "Labels": "com.docker.compose.service=crypto,com.docker.compose.project=harpoon-cloud"}]
        code, _, err = self.run_cli("install")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "OTHER_HARPOON_RUNTIME_ACTIVE_STOP_EXPLICITLY_FIRST")
        self.assertFalse(any("build" in c[0] for c in self.fake.calls))

    def test_conflict_recheck_after_build_catches_new_legacy_start(self):
        self.fake.on_build = lambda: self.fake.containers.append({"Names": "legacy", "Labels": "com.docker.compose.service=equity,com.docker.compose.project=harpoon-cloud"})
        self.assertEqual(self.run_cli("install")[0], 2)
        self.assertFalse(any("up" in c[0] for c in self.fake.calls))

    def test_another_ultimate_project_is_rejected(self):
        self.fake.containers = [{"Names": "other", "Labels": "com.docker.compose.service=xxxultimate,com.docker.compose.project=another"}]
        code, _, err = self.run_cli("install")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "ANOTHER_HARPOON_PROJECT_ACTIVE")

    def test_configuration_changed_during_build_is_not_started(self):
        self.fake.on_build = lambda: self.mutate_config(capitalLimit=19999)
        code, _, err = self.run_cli("install")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "CONFIG_CHANGED_DURING_BUILD")
        self.assertFalse(any("up" in c[0] for c in self.fake.calls))

    def test_config_or_build_failure_never_leaks_output_or_starts(self):
        for stage in ("config", "build"):
            self.fake = FakeDocker()
            self.fake.fail_stage = stage
            code, out, err = self.run_cli("install")
            self.assertEqual(code, 2)
            self.assertNotIn(SECRET, out + err)
            self.assertNotIn(PASSWORD, out + err)
            self.assertFalse(any("up" in c[0] for c in self.fake.calls))

    def test_status_needs_no_credentials_does_not_dump_logs_or_commands(self):
        self.fake.status = [{"Service": "xxxultimate", "State": "running", "Health": "healthy", "Command": SECRET, "Labels": PASSWORD}]
        code, out, _ = self.run_cli("status", env={})
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["health_meaning"], "HTTP_ALIVE_ONLY")
        self.assertFalse(result["runtime_readiness_verified"])
        self.assertFalse(any("logs" in x[0] or "up" in x[0] or "stop" in x[0] for x in self.fake.calls))

    def test_stop_warns_and_never_deletes_data_or_sends_orders(self):
        code, out, _ = self.run_cli("stop", env={})
        self.assertEqual(code, 0)
        self.assertIn("interrumpe la protección", out)
        self.assertEqual(self.fake.calls[-1][0][-2:], ["stop", "xxxultimate"])
        self.assertFalse(any("down" in x[0] or "rm" in x[0] for x in self.fake.calls))

    def test_explicit_legacy_preserves_existing_compose(self):
        legacy = self.write_legacy()
        original = legacy.read_bytes()
        code, out, _ = self.run_cli("install", "--legacy", "--plan", env={})
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["mode"], "LEGACY_EXPLICIT")
        self.assertTrue(result["compose_file"].endswith("/compose.json"))
        self.assertEqual(legacy.read_bytes(), original)
        self.assertEqual(self.fake.calls, [])

    def test_missing_legacy_config_never_runs_old_configurator(self):
        code, _, err = self.run_cli("install", "--legacy", env={})
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "LEGACY_EXISTING_COMPOSE_REQUIRED")
        self.assertEqual(self.fake.calls, [])

    def test_legacy_start_is_blocked_by_active_ultimate(self):
        self.write_legacy()
        self.fake.containers = [{"Names": "harpoon-xxxultimate", "Labels": "com.docker.compose.service=xxxultimate,com.docker.compose.project=harpoon-xxxultimate"}]
        self.assertEqual(self.run_cli("install", "--legacy", env={})[0], 2)
        self.assertFalse(any("build" in c[0] for c in self.fake.calls))

    def test_duplicate_json_and_nonfinite_config_are_rejected_locally(self):
        for source in ('{"mode":"paper","mode":"live"}', '{"x":NaN}', '{"x":1e999}'):
            self.config.write_text(source)
            self.assertEqual(self.run_cli("install", "--check")[0], 2)
            self.assertEqual(self.fake.calls, [])

    def test_compose_v1_and_command_errors_are_controlled(self):
        self.fake.version = "1.29.2"
        self.assertEqual(self.run_cli("install")[0], 2)
        self.assertEqual(len(self.fake.calls), 1)
        output, errors = io.StringIO(), io.StringIO()
        def unavailable(*args, **kwargs):
            raise FileNotFoundError(SECRET)
        code = installer.main(["status"], root=self.root, environment={}, runner=unavailable, output=output, errors=errors)
        self.assertEqual(code, 2)
        self.assertNotIn(SECRET, errors.getvalue())


if __name__ == "__main__":
    unittest.main()
