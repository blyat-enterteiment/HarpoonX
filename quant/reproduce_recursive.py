"""Reproduce synthetic engineering behavior only; never a profit forecast."""

from __future__ import annotations

import json
import runpy
import tempfile
import time
from pathlib import Path

from harpoon_quant.optimization import Policy, replay
from harpoon_quant.performance import report
from harpoon_quant.recursive import active_policy, tick

ROOT = Path(__file__).resolve().parent


def main() -> None:
    fixture = runpy.run_path(str(ROOT / "tests/test_recursive.py"))["fixture"]
    history = []
    elapsed = []
    result = {}
    for repeat in range(3):
        with tempfile.TemporaryDirectory() as folder:
            panel, config, binding = fixture(folder)
            started = time.perf_counter()
            steps = []
            for _ in range(8):
                result = tick(
                    panel, config, binding, "2026-09-21T00:00:00+00:00", paper=True
                )
                steps.append(result)
                if result["status"] in {"RESEARCH_ACCEPTED", "REJECTED", "EXHAUSTED"}:
                    break
            elapsed.append(time.perf_counter() - started)
            assert result["status"] == "RESEARCH_ACCEPTED", result["status"]
            assert not (
                active_policy(config["statePath"], binding, "2026-09-21T00:00:00+00:00")
                or {}
            ).get("policy")
            if repeat == 0:
                history = steps
                target = ROOT / "examples/recursive"
                (target / "panel.synthetic.json").write_text(
                    json.dumps(panel, indent=2) + "\n"
                )
                config["statePath"] = "evidence/demo_optimizer.sqlite3"
                envelope = dict(
                    panel=panel,
                    config=config,
                    binding=binding,
                    asof="2026-09-21T00:00:00+00:00",
                    paper=True,
                )
                (target / "envelope.synthetic.json").write_text(
                    json.dumps(envelope, indent=2) + "\n"
                )
                settings = dict(binding["risk_limits"], origin=panel["origin"])
                base = replay(panel["development"], Policy(), settings)
                performance = dict(
                    origin=panel["origin"],
                    return_basis="NET_FLOW_ADJUSTED",
                    returns=base["returns"],
                    times=[d + "T23:59:59+00:00" for d in panel["development"]["days"]],
                    initial_equity=20000,
                    periods_per_year=365,
                    sampling="DAILY_UTC_CALENDAR",
                    trades=base["trades"],
                )
                (target / "performance.synthetic.json").write_text(
                    json.dumps(performance, indent=2) + "\n"
                )
                (ROOT / "evidence/recursive_performance.synthetic.json").write_text(
                    json.dumps(report(performance), indent=2) + "\n"
                )
    evidence = dict(
        origin="SYNTHETIC_ENGINEERING_ONLY",
        scope="Artificial selection fixture, not empirical financial alpha. Complete loop CPU and SQLite I/O; excludes broker/API and worker start.",
        cycle_seconds=elapsed,
        steps=history,
        status=result["status"],
        active_policy=None,
    )
    (ROOT / "evidence/recursive_demo.synthetic.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print(
        json.dumps(
            dict(
                status=result["status"],
                iterations=len(history),
                seconds=elapsed,
                active_policy=None,
            )
        )
    )


if __name__ == "__main__":
    main()
