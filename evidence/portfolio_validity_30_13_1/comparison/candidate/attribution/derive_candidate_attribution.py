"""Attribute a closed registered result. No strategy execution or new trial."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANDIDATE = ROOT.parent
CONTINUATION = ROOT.parents[2]
SOURCE = CONTINUATION / "attribution/attribute_funded_portfolio.py"
SOURCE_TEXT = SOURCE.read_text()
protected = [CANDIDATE / "result.json", CANDIDATE / "reproduction_capture.json",
             CANDIDATE / "continuous_portfolio_curve.json", CANDIDATE / "funded_campaigns.json"]
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
replacements = {
    'capture = json.loads((ROOT / "reproduction_capture.json").read_text())':
        'capture = json.loads((ROOT.parent / "reproduction_capture.json").read_text())',
    'verification = json.loads((ROOT / "reproduction_verification.json").read_text())':
        'receipt = json.loads((ROOT.parent / "result.json").read_text())',
    'assert verification["identical"]':
        'assert receipt["result"]["status"] == "COMPLETE_EXPLORATORY_ONLY" and receipt["financial_acceptance_allowed"] is False',
    'assert capture["verifiedAgainstFrozenReport"]':
        'assert capture["funded"] == receipt["result"]["funded"] and receipt["mode"] == "candidate"',
    'verification["portfolio"]["netUsd"]': 'receipt["result"]["portfolio"]["netUsd"]',
    'DESCRIPTIVE_ATTRIBUTION_OF_FROZEN_REPRODUCED_MODELED_PORTFOLIO':
        'DESCRIPTIVE_ATTRIBUTION_OF_CLOSED_REGISTERED_CANDIDATE_NO_NEW_TRIAL',
    'CLOSED_CHANNEL deadline is opened+72h; replayCampaign closes at the first future bar at/after deadline. Weekends, holidays and closed sessions can extend actual modeled holding beyond72h.':
        'Calendar-constrained deadline is planned from decision time and rounded earlier to the executable grid. Actual modeled holding is measured from the retained fills.',
    'The positive historical aggregate cannot be represented as compliant with a strict72h maximum. No counterfactual early close or exclusion PnL is inferred here.':
        'These are measurements of the closed candidate result, not a guarantee about future execution. This attribution does not rerun alternative exits.',
    'No changed policy, exclusion or reallocation is evaluated. Descriptive contribution is not the counterfactual result of removing an asset or time window.':
        'This attribution does not run another policy, exclusion or reallocation. It reads the completed registered candidate; descriptive contribution is not a counterfactual removal result.',
}
adapted = SOURCE_TEXT
for previous, replacement in replacements.items():
    assert adapted.count(previous) == 1, previous
    adapted = adapted.replace(previous, replacement)
namespace = {"__name__": "candidate_attribution_derivation", "__file__": str(Path(__file__).resolve())}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(adapted, str(SOURCE), "exec"), namespace)

receipt = json.loads((CANDIDATE / "result.json").read_text())
candidate = json.loads((ROOT / "portfolio_attribution.json").read_text())
baseline = json.loads((CONTINUATION / "attribution/portfolio_attribution.json").read_text())
old_trades = json.loads((CONTINUATION / "attribution/funded_campaigns.json").read_text())["campaigns"]
new_trades = json.loads((ROOT / "funded_campaigns.json").read_text())["campaigns"]
old = {t["id"]: t for t in old_trades}
new = {t["id"]: t for t in new_trades}
common_ids = sorted(old.keys() & new.keys())
new_ids = sorted(new.keys() - old.keys())
removed_ids = sorted(old.keys() - new.keys())
frozen = json.loads((ROOT.parents[1] / "frozen_study.json").read_text())
signals = {s["id"]: s for s in frozen["common"]}


def slim(trade):
    return {k: trade[k] for k in ["id", "symbol", "hypothesis", "policy", "opened_utc", "closed_utc", "quantity", "netUsd", "holding_hours", "entry_window"]}


introduced = []
for ident in new_ids:
    signal = signals[ident]
    occupied = [t for t in old_trades if t["symbol"] == signal["symbol"] and t["opened"] <= signal["at"] < t["closed"]]
    introduced.append({"campaign": slim(new[ident]), "signal_decision_at": signal["at"],
                       "baseline_same_symbol_active_at_decision": [slim(t) for t in occupied],
                       "interpretation": "Recorded new campaign under the compound correction. A baseline open campaign on the same symbol explains the old SYMBOL_BUSY condition when present; no separate causal effect size is estimated."})

common_delta = sum(new[i]["netUsd"] - old[i]["netUsd"] for i in common_ids)
introduced_pnl = sum(new[i]["netUsd"] for i in new_ids)
removed_component = -sum(old[i]["netUsd"] for i in removed_ids)
delta = candidate["net_modeled_trading_pnl_usd"] - baseline["net_modeled_trading_pnl_usd"]
assert math.isclose(delta, common_delta + introduced_pnl + removed_component, abs_tol=1e-9)


def compare_groups(field):
    a = {x["group"]: x for x in baseline[field]}
    b = {x["group"]: x for x in candidate[field]}
    return [{"group": key, "baseline_campaigns": a.get(key, {}).get("campaigns", 0),
             "candidate_campaigns": b.get(key, {}).get("campaigns", 0),
             "baseline_pnl_usd": a.get(key, {}).get("net_pnl_usd", 0),
             "candidate_pnl_usd": b.get(key, {}).get("net_pnl_usd", 0),
             "difference_usd": b.get(key, {}).get("net_pnl_usd", 0) - a.get(key, {}).get("net_pnl_usd", 0)}
            for key in sorted(a.keys() | b.keys())]


summary = {
    "schema": "HARPOON_CLOSED_CANDIDATE_ATTRIBUTION_DELTA_1",
    "scope": "READ_ONLY_DERIVATION_NO_NEW_FINANCIAL_TRIAL",
    "trial_id": receipt["registration"]["trial_id"],
    "new_financial_trials_in_this_derivation": 0,
    "candidate_result_status": receipt["result"]["status"],
    "financial_acceptance_allowed": False,
    "period": candidate["period"],
    "baseline_pnl_usd": baseline["net_modeled_trading_pnl_usd"],
    "candidate_pnl_usd": candidate["net_modeled_trading_pnl_usd"],
    "delta_usd": delta,
    "baseline_campaigns": len(old), "candidate_campaigns": len(new),
    "common_campaigns": len(common_ids), "introduced_campaigns": len(new_ids), "absent_campaigns": len(removed_ids),
    "algebraic_reconciliation_only": {"common_campaign_delta_usd": common_delta,
                                      "introduced_campaign_pnl_usd": introduced_pnl,
                                      "absent_campaign_component_usd": removed_component,
                                      "sum_usd": common_delta + introduced_pnl + removed_component},
    "by_asset": compare_groups("by_asset"),
    "by_entry_window": compare_groups("by_entry_window"),
    "by_exit_window": compare_groups("by_exit_window"),
    "by_hypothesis_policy": compare_groups("by_hypothesis_policy"),
    "candidate_holding": candidate["holding_limit_diagnostic"],
    "candidate_concentration": candidate["concentration"],
    "introduced_campaigns_detail": introduced,
    "absent_campaigns_detail": [slim(old[i]) for i in removed_ids],
    "common_campaign_changes": [{"id": i, "symbol": new[i]["symbol"],
                                 "baseline_quantity": old[i]["quantity"], "candidate_quantity": new[i]["quantity"],
                                 "baseline_closed_utc": old[i]["closed_utc"], "candidate_closed_utc": new[i]["closed_utc"],
                                 "baseline_pnl_usd": old[i]["netUsd"], "candidate_pnl_usd": new[i]["netUsd"],
                                 "difference_usd": new[i]["netUsd"] - old[i]["netUsd"]}
                                for i in common_ids if any(new[i][k] != old[i][k] for k in ["quantity", "closed", "netUsd"])],
    "attribution_limit": "The delta belongs to the registered compound correction (calendar+causal sizing+fixed-quantity fill validation and capital interactions). It is not an isolated effect estimate of either correction or of removing an asset/window.",
    "window_limit": "Entry/exit cohorts receive complete campaign PnL, not PnL earned only during those90minutes. After-close90minutes are not evaluated.",
    "source_method": {"reused_attribution_script": str(SOURCE), "sha256": hashlib.sha256(SOURCE_TEXT.encode()).hexdigest(),
                      "adapter_substitutions": replacements},
    "source_receipt_sha256": hashlib.sha256((CANDIDATE / "result.json").read_bytes()).hexdigest(),
}
candidate["source_trial_id"] = receipt["registration"]["trial_id"]
candidate["source_result_sha256"] = summary["source_receipt_sha256"]
(ROOT / "portfolio_attribution.json").write_text(json.dumps(candidate, indent=2) + "\n")
(ROOT / "comparison_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
assert before == after, "Source result or capture changed"
manifest = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
            for p in sorted(ROOT.iterdir()) if p.is_file() and p.name != "manifest.json"}
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({k: summary[k] for k in ["trial_id", "baseline_pnl_usd", "candidate_pnl_usd", "delta_usd", "common_campaigns", "introduced_campaigns", "absent_campaigns", "algebraic_reconciliation_only", "by_asset", "by_entry_window"]}, indent=2))
