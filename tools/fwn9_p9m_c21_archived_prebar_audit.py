#!/usr/bin/env python3
"""C21 offline archived source-state identifiability audit, READ-ONLY.

Reads exactly ONE SHA-verified pre-existing WEAK development member of the
original M9 ZIP. Does not inspect/open any final member, run the generator,
produce strategies, reuse a broker, or execute any economic account.
The absence of prebar stops/targets is a factual schema finding, NOT a theorem
that their law is mathematically unknowable from the frozen generator+policy.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

ARCHIVE_SHA="a1d7a78c81f16b357a8699369fa1c8ac66e2b48e90d33f0770ebad88e3e0fc92"
MEMBER="evidence/modulation9/development/WEAK_730101.json.gz"
MEMBER_SHA="4c45a1177a063ae4b7758ef3a644c9dbc1c1c3925d30a15d0a152f392adde819"
REQUIRED_PREBAR=(
    "bar_open_knownAt", "stop_before_bar", "targets_before_bar",
    "target_quantities_before_bar", "pending_stop_knownAt",
    "original_IOC_decision_snapshot", "original_funded_reservations",
    "exchange_executed_bid_ask_and_depth_receipt"
)
REASONS=("STOP","TP1","TP2","TIME","MODULATION9_STALLED")
SCHEMA="HARPOON_M11_C21_ORIGINAL_ARCHIVED_PREBAR_STATE_SCHEMA_AUDIT_1"


def sha_file(path: Path)->str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def inspect_history(h:dict[str,Any])->dict[str,Any]:
    if (h.get("world")!="WEAK" or h.get("stage")!="development" or
        h.get("seed")!=730101 or not isinstance(h.get("accounts"),list) or
        len(h["accounts"])!=78):
        raise ValueError("C21_REGISTERED_EXISTING_DEVELOPMENT_ONLY")
    counts:Counter[str]=Counter()
    scenarios:Counter[str]=Counter()
    observed_keys: set[str]=set()
    exit_keys:set[str]=set()
    economic_accounts=0
    ntrades=0
    nfills=0
    for account in h["accounts"]:
        scenario=account.get("scenario")
        if scenario not in ("NOMINAL","STRESS"):
            raise ValueError("C21_ARCHIVED_SCENARIO")
        scenarios[scenario]+=1
        if account.get("terminal_reconciled") is not True:
            raise ValueError("C21_ORIGINAL_TERMINAL_ACCOUNT_NOT_RECONCILED")
        if not isinstance(account.get("trades"),list):
            raise ValueError("C21_ARCHIVED_TRADES_REQUIRED")
        economic_accounts+=1
        for trade in account["trades"]:
            observed_keys.update(trade)
            if not isinstance(trade.get("exit_fills"),list):
                raise ValueError("C21_ORIGINAL_EXIT_RECEIPTS_REQUIRED")
            ntrades+=1
            if (trade.get("opened",float("inf")) >
                trade.get("closed",float("-inf"))):
                raise ValueError("C21_ORIGINAL_LOT_CLOCK")
            for fill in trade["exit_fills"]:
                exit_keys.update(fill)
                if fill.get("reason") not in REASONS:
                    raise ValueError("C21_ORIGINAL_REASON_UNEXPECTED")
                if fill["known_at"]<fill["at"]:
                    raise ValueError("C21_FUTURE_RECEIPT")
                counts[fill["reason"]]+=1
                nfills+=1
    if (economic_accounts,ntrades,nfills,scenarios["NOMINAL"],
        scenarios["STRESS"])!=(78,1213,1641,39,39):
        raise ValueError("C21_PREVIOUS_SOURCE_EVENT_COUNTS_CHANGED")
    missing=[field for field in REQUIRED_PREBAR if
             field not in observed_keys and field not in exit_keys]
    if len(missing)!=len(REQUIRED_PREBAR):
        raise ValueError("C21_PREBAR_ARCHIVE_SCHEMA_UNEXPECTEDLY_CHANGED")
    if sum(counts[r] for r in ("STOP","TP1","TP2"))!=1430:
        raise ValueError("C21_HISTORICAL_BARRIER_COUNT_CHANGED")
    return {
        "schema":SCHEMA,
        "historical_archive_member":MEMBER,
        "scope":"ALREADY_EXECUTED_SINGLE_WEAK_DEV_SEED_NOT_POPULATION",
        "registered_world":"WEAK",
        "registered_seed":730101,
        "existing_economic_accounts_READ_ONLY":economic_accounts,
        "existing_trades_READ_ONLY":ntrades,
        "existing_exit_fills_READ_ONLY":nfills,
        "scenario_counts":dict(scenarios),
        "existing_original_barrier_fills":1430,
        "original_exit_reason_counts":dict(counts),
        "historical_compact_trade_fields":sorted(observed_keys),
        "historical_compact_exit_fill_fields":sorted(exit_keys),
        "missing_required_original_prebar_or_exchange_fields":missing,
        "full_prebar_state_distribution_from_compact_archive_certifiable":False,
        "WEAK_population_accepted_admissions_expectation_certified":False,
        "WEAK_population_U_expectation_certified":False,
        "ordered_8step_tape_exists_separately":True,
        "broker_fill_attainability_certified":False,
        "mathematically_unknowable_from_all_source_code":False,
        "no_final_member_opened":True,
        "budget":{"new_market_seeds":0,"new_signals":0,
                  "new_economic_accounts":0,"opened_M10_final":0},
        "N9S":"NO_GO"
    }


def audit_one_existing_development_member(archive:Path)->dict[str,Any]:
    if sha_file(archive)!=ARCHIVE_SHA:
        raise ValueError("C21_ORIGINAL_M9_ZIP_SHA256")
    # Only the literal pre-registered development member is touched.
    # zipfile reads the central directory automatically, not final data bytes.
    with zipfile.ZipFile(archive) as z:
        with z.open(MEMBER) as stream:
            blob=stream.read()
    if hashlib.sha256(blob).hexdigest()!=MEMBER_SHA:
        raise ValueError("C21_REGISTERED_DEVELOPMENT_MEMBER_SHA256")
    h=json.loads(gzip.decompress(blob))
    out=inspect_history(h)
    out["original_archive_SHA256"]=ARCHIVE_SHA
    out["original_member_SHA256"]=MEMBER_SHA
    return out


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    out=audit_one_existing_development_member(args.archive)
    rendered=json.dumps(out,sort_keys=True,indent=2)+"\n"
    if args.output is not None:
        args.output.write_text(rendered,encoding="utf-8")
    print("C21_ARCHIVED_PREBAR_IDENTIFIABILITY="+json.dumps({
        k:v for k,v in out.items() if k not in (
            "historical_compact_trade_fields",
            "historical_compact_exit_fill_fields"
        )
    },sort_keys=True))


if __name__=="__main__":
    main()
