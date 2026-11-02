"""Terminal evaluation of a sealed candidate; no new trials or changed gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.special import ndtri

ROOT = Path(__file__).resolve().parent
# The validator is current; the recorded simulation remains in its frozen copy.
sys.path.insert(0, str(ROOT.parent))
from harpoon_quant.recursive import Journal  # noqa: E402
from harpoon_quant.study_integrity import (  # noqa: E402
    VerifiedStudy,
    assert_inputs_unchanged,
    load_verified_study,
)


def decide(
    mean_net: float,
    mean_growth: float,
    improvement_growth: float,
    lcb_all: bool,
    dd_ok: bool,
    costs_ok: bool,
    closures_ok: bool,
) -> str:
    if not all(math.isfinite(x) for x in (mean_net, mean_growth, improvement_growth)):
        raise ValueError("NONFINITE_DECISION_INPUT")
    if mean_net <= 0 or mean_growth <= 0:
        return "REJECTED"
    if not all([improvement_growth > 0, lcb_all, dd_ok, costs_ok, closures_ok]):
        return "INSUFFICIENT_EVIDENCE"
    return "RESEARCH_ACCEPTED_SYNTHETIC_ONLY"


def decision_text(status: str, mean_net: float) -> str:
    if status == "REJECTED":
        if mean_net < 0:
            return "Reject frozen candidate and retain existing baseline runtime; cash was superior on mean in this synthetic test. No operational policy activated."
        return "Reject frozen candidate: positive net profit and positive log growth are both required. No operational policy activated."
    if status == "INSUFFICIENT_EVIDENCE":
        return "Positive synthetic net profit is insufficient: at least one registered validation gate failed. No operational policy activated."
    if status == "RESEARCH_ACCEPTED_SYNTHETIC_ONLY":
        return "The frozen candidate passed the registered synthetic research gates. This does not establish real-market profitability or authorize an operational policy."
    raise ValueError("UNKNOWN_DECISION_STATUS")


def _calculate(study: VerifiedStudy) -> dict[str, Any]:
    """Keep the historical numerical analysis and acceptance thresholds intact."""
    a, h = study.analysis, study.holdout
    sessiondates = {x["date"] for x in study.calendar["calendar"]}
    comparisons: dict[str, Any] = {}
    seedrows = []
    for name in h["results"][0]["runs"]:
        runs = [r["runs"][name] for r in h["results"]]
        pnls = np.array(
            [r["metrics"]["net_profit_usd_on_adjusted_initial_capital"] for r in runs]
        )
        g = np.array([r["mean_log_growth"] for r in runs])
        comparisons[name] = dict(
            mean_pnl_usd=float(pnls.mean()),
            median_pnl_usd=float(np.median(pnls)),
            min_pnl_usd=float(pnls.min()),
            max_pnl_usd=float(pnls.max()),
            mean_return=float(pnls.mean() / 20000),
            mean_daily_log_growth=float(g.mean()),
            median_sortino=float(
                np.median(
                    [
                        r["metrics"]["sortino_per_period"]
                        for r in runs
                        if r["metrics"]["sortino_per_period"] is not None
                    ]
                )
            ),
            max_drawdown_across_paths=max(r["metrics"]["max_drawdown"] for r in runs),
            mean_cvar95_fraction=float(
                np.mean([r["metrics"]["historical_cvar95_fraction"] for r in runs])
            ),
            cost_mean_usd=float(np.mean([r["metrics"]["net_costs_usd"] for r in runs])),
            closures=sum(r["metrics"]["trade_count"] for r in runs),
            positive_paths=int((pnls > 0).sum()),
            stock_closures=sum(t["kind"] == "stock" for r in runs for t in r["trades"]),
        )
    base, cand = [], []
    for row in h["results"]:
        b, c = row["runs"]["baseline"], row["runs"]["candidate"]
        take = np.array([date in sessiondates for date in b["dates"]])
        base.append(np.log1p(np.array(b["returns"]))[take])
        cand.append(np.log1p(np.array(c["returns"]))[take])
        seedrows.append(
            dict(
                seed=row["seed"],
                baseline=b["metrics"],
                candidate=c["metrics"],
                growth_baseline=b["mean_log_growth"],
                growth_candidate=c["mean_log_growth"],
            )
        )
    diff = np.asarray(cand) - np.asarray(base)
    paths, n = diff.shape
    family, reps = a["family_bound"], a["bootstrap_repetitions"]
    intervals: dict[str, Any] = {}
    for block in a["block_lengths_sessions"]:
        rng = np.random.default_rng(887700 + block)
        draws = []
        for lo in range(0, reps, 256):
            batch = min(256, reps - lo)
            ids = rng.integers(0, paths, (batch, paths))
            starts = rng.integers(0, n, (batch, paths, (n + block - 1) // block))
            idx = ((starts[:, :, :, None] + np.arange(block)) % n).reshape(
                batch, paths, -1
            )[:, :, :n]
            values = diff[ids[:, :, None], idx]
            draws.extend(values.mean(axis=(1, 2)).tolist())
        intervals[str(block)] = dict(
            lcb_family_95=float(np.quantile(draws, 0.05 / family)),
            paired_mean=float(diff.mean()),
            interval_descriptive_95=np.quantile(draws, [0.025, 0.975]).tolist(),
            repetitions=reps,
        )
    centered = diff - diff.mean()
    v0 = float(np.mean(centered**2))
    hac = v0
    for lag in range(1, min(11, n)):
        hac += (
            2 * (1 - lag / 11) * float(np.mean(centered[:, :-lag] * centered[:, lag:]))
        )
    effective = min(paths * n, paths * n * v0 / max(hac, 1e-30)) if v0 > 0 else None
    perseed = diff.mean(axis=1)
    se = float(np.std(perseed, ddof=1) / np.sqrt(paths))
    mde = float((ndtri(1 - 0.05 / family) + ndtri(0.8)) * se)
    b, c = comparisons["baseline"], comparisons["candidate"]
    improve = c["mean_daily_log_growth"] - b["mean_daily_log_growth"]
    costs_ok = all(comparisons[k]["min_pnl_usd"] > 0 for k in ["cost_1_5", "cost_2"])
    dd_ok = all(
        r["candidate"]["max_drawdown"] <= r["baseline"]["max_drawdown"]
        and r["candidate"]["max_drawdown"] <= 0.08
        for r in seedrows
    )
    closures_ok = all(r["candidate"]["trade_count"] >= 20 for r in seedrows)
    lcb_all = all(v["lcb_family_95"] > 0 for v in intervals.values())
    status = decide(
        c["mean_pnl_usd"],
        c["mean_daily_log_growth"],
        improve,
        lcb_all,
        dd_ok,
        costs_ok,
        closures_ok,
    )
    return dict(
        status=status,
        evidence_type="ESTIMACION_SINTETICA_NO_OBSERVADA",
        comparisons=comparisons,
        seed_results=seedrows,
        incremental_mean_pnl_usd=c["mean_pnl_usd"] - b["mean_pnl_usd"],
        incremental_mean_log_growth=improve,
        inference=dict(
            block_intervals=intervals,
            independent_synthetic_paths=paths,
            paired_sessions_per_path=n,
            HAC_effective_time_observations=effective,
            approx_MDE_daily_log_return_80pct=mde,
            measured_effect_daily_session_log=float(diff.mean()),
            family_bound=family,
            psr_dsr="Diagnostic only; no observed complete trading track record; do not treat as proof of alpha.",
            limitation="HAC/normal MDE and hierarchical resampling on five artificial paths are approximate; no real-market probability estimate. Inference detail fixed before numeric inspection but after holdout generation.",
        ),
        gates=dict(
            net_positive=c["mean_pnl_usd"] > 0,
            log_growth_positive=c["mean_daily_log_growth"] > 0,
            improvement_positive=improve > 0,
            lcb_positive_all_blocks=lcb_all,
            drawdown_no_worse_all_paths=dd_ok,
            cost_stress_positive_all_paths=costs_ok,
            minimum_20_closures_each=closures_ok,
        ),
        cash=dict(
            pnl=0,
            return_fraction=0,
            scope="Zero interest cash benchmark assumption, not a quoted cash yield",
        ),
        execution_allowed=False,
        observed_profit=None,
        decision=decision_text(status, c["mean_pnl_usd"]),
        warnings=[
            "Nearly all candidate closures are stocks; no positive options advantage established.",
            "Development and holdout seeds differ; synthetic DGP still shares a designed generator family.",
            "Gap/IV scenarios are liquidation mark haircuts; delay is an edge buffer and outage blocks entries. They are approximations, not full market-impact/queue/network replay.",
            "FOK/depth/age are synthetic inputs. D inherits matched-option spread screening when selecting underlying; real stock-book validation remains pending.",
            "Account permissions cannot be verified by the available data-only connector; OPRA subscription denied.",
            "The legacy original archive was truncated; its journal was reconstructed with same script and matching results, not recovered as an authenticated original.",
        ],
        integrity=dict(
            status="SEALED_INPUTS_AND_ACCOUNTING_VERIFIED",
            source_sha256=study.source_hashes,
            research_budget=study.budget,
            verified_runs=sum(len(row["runs"]) for row in h["results"]),
            scope="Local journal and frozen-input integrity; metrics reconciled against returns, NAV, entries and separate exit trades. No provider authenticity or executable-fill claim.",
        ),
        scenario_roles=dict(
            acceptance_cost_stress=["cost_1_5", "cost_2"],
            descriptive_only=["gaps", "iv_crush", "liquidity", "delay", "outage"],
            scope="Historical registered gates are unchanged. Additional scenario gates require a newly registered study; no retroactive acceptance changes.",
        ),
    )


def analyze_study(directory: Path) -> dict[str, Any]:
    """Read-only analysis; malformed or altered inputs fail before deciding."""
    study = load_verified_study(directory)
    result = _calculate(study)
    assert_inputs_unchanged(study)
    return result


def _replace_decision(directory: Path, content: str) -> None:
    """Atomically replace this one file; SQLite is a separate resource."""
    path = directory / "study/decision.json"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as staged:
            temporary = Path(staged.name)
            staged.write(content)
            staged.flush()
            os.fsync(staged.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _finish_publication(
    journal: Journal, study: VerifiedStudy, record: dict[str, Any]
) -> None:
    """A crash/failure leaves a detectable PENDING receipt for explicit recovery."""
    with journal.transaction():
        if journal.get("economic:decision") != record:
            raise ValueError("DECISION_PUBLICATION_CHANGED")
        assert_inputs_unchanged(study, allow_pending=True)
        content = record["artifact_content"]
        if hashlib.sha256(content.encode()).hexdigest() != record["result_hash"]:
            raise ValueError("PENDING_DECISION_CONTENT_HASH")
        _replace_decision(study.root, content)
        journal.put(
            "economic:decision",
            dict(record, publication_state="COMPLETE"),
            datetime.now(UTC).isoformat(),
        )


def recover_pending_publication(directory: Path) -> dict[str, Any]:
    """Publish an already computed sealed result; no recalculation or new trial."""
    study = load_verified_study(directory, allow_pending=True)
    journal = Journal(directory / "study/optimizer.sqlite3")
    try:
        record = journal.get("economic:decision")
        if not isinstance(record, dict) or record.get("publication_state") != "PENDING":
            raise ValueError("NO_PENDING_DECISION_PUBLICATION")
        if (
            record.get("input_sha256") != study.source_hashes
            or record.get("research_budget") != study.budget
        ):
            raise ValueError("PENDING_DECISION_INPUTS_CHANGED")
        _finish_publication(journal, study, record)
        return json.loads(record["artifact_content"])
    finally:
        journal.close()


def main(directory: Path = ROOT) -> None:
    study = load_verified_study(directory)
    result = _calculate(study)
    content = json.dumps(result, indent=2, allow_nan=False) + "\n"
    record = dict(
        status=result["status"],
        result_hash=hashlib.sha256(content.encode()).hexdigest(),
        active=False,
        input_sha256=study.source_hashes,
        research_budget=study.budget,
        publication_state="PENDING",
        artifact_content=content,
    )
    # Register PENDING durably before changing the published file. Revalidate
    # while holding the SQLite write lock, so another legitimate writer cannot
    # change the study budget between the check and this reservation.
    journal = Journal(directory / "study/optimizer.sqlite3")
    try:
        with journal.transaction():
            assert_inputs_unchanged(study)
            journal.put("economic:decision", record, datetime.now(UTC).isoformat())
        _finish_publication(journal, study, record)
    finally:
        journal.close()
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key
                in {
                    "status",
                    "comparisons",
                    "incremental_mean_pnl_usd",
                    "gates",
                    "inference",
                    "integrity",
                    "scenario_roles",
                }
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT)
    parser.add_argument("--recover-publication", action="store_true")
    args = parser.parse_args()
    if args.recover_publication:
        recovered = recover_pending_publication(args.directory)
        print(json.dumps(dict(publication="RECOVERED", status=recovered["status"])))
    else:
        main(args.directory)
