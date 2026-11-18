"""HF15 bounded conservative quote-markout research; NOT execution evidence.
Reads authenticated HF20 tape tar.gz and re-verifies per-page SHA256 manifests.
Does not claim SIP completeness, actual fills, causal entry signal or economic alpha.
"""
import argparse
import hashlib
import io
import json
import math
import tarfile

INITIAL_WEALTH = 20000.0
NOTIONAL = 1000.0
SIDE_COST_BPS = (12.5, 30.0)
MAX_SPREAD_BPS = 100.0
MIN_SIZE = 100

def evaluate(tape: bytes):
    with tarfile.open(fileobj=io.BytesIO(tape), mode="r:gz") as archive:
        members = {m.name: m for m in archive.getmembers()}
        if any(not m.isfile() or m.name.startswith("/") or ".." in m.name.split("/") for m in members.values()):
            raise ValueError("Unsafe archive member")
        def read(name):
            if name not in members:
                raise ValueError("Missing archive member: " + name)
            return archive.extractfile(members[name]).read()
        pages = {}
        provenance = {}
        for kind in ("quotes", "trades"):
            manifest_raw = read(kind + "/manifest.json")
            manifest = json.loads(manifest_raw)
            if manifest["status"] != "PROVIDER_PAGINATION_EXHAUSTED_NOT_FULL_MARKET_CERTIFIED":
                raise ValueError("Uncertified provider pagination")
            if manifest["source"] != "Alpaca IEX Market Data v2":
                raise ValueError("Unexpected venue")
            if manifest["symbol"] != "AAPL":
                raise ValueError("Unexpected symbol")
            records = []
            for entry in manifest["page_hashes"]:
                raw = read(kind + "/page_%05d.json" % entry["page"])
                if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                    raise ValueError("Page hash mismatch")
                block = json.loads(raw)[kind]
                if len(block) != entry["records"]:
                    raise ValueError("Page count mismatch")
                records.extend(block)
            if len(records) != manifest["records"]:
                raise ValueError("Total count mismatch")
            pages[kind] = records
            provenance[kind] = {"manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                                "records": len(records), "pages": len(manifest["page_hashes"])}
    quotes = pages["quotes"]
    valid = []
    for q in quotes:
        try:
            bid, ask = float(q["bp"]), float(q["ap"])
            bs, az = float(q["bs"]), float(q["as"])
            mid = (bid + ask) / 2
            spread_bps = 10000 * (ask - bid) / mid
            if not all(math.isfinite(x) for x in (bid, ask, bs, az, spread_bps)):
                continue
            if bid <= 0 or ask <= bid or bs < MIN_SIZE or az < MIN_SIZE:
                continue
            if spread_bps > MAX_SPREAD_BPS:
                continue
            valid.append(q)
        except (KeyError, ValueError, TypeError, ZeroDivisionError):
            continue
    result = {"status": "EXPLORATORY_SHADOW_ONLY", "source": "Alpaca IEX",
              "quote_count": len(quotes), "eligible_quote_count": len(valid),
              "trade_count": len(pages["trades"]), "provenance": provenance,
              "cash_benchmark_usd": INITIAL_WEALTH,
              "original_benchmark": "UNAVAILABLE_FOR_THIS_ONE_MINUTE_TAPE",
              "causal_signal": "NOT_ESTABLISHED", "actual_fills": 0}
    if len(valid) < 2:
        result["scenario"] = "NO_ADMISSIBLE_TWO_SIDED_QUOTES"
        return result
    first, last = valid[0], valid[-1]
    entry_ask, exit_bid = float(first["ap"]), float(last["bp"])
    shares = min(NOTIONAL / entry_ask, float(first["as"]), float(last["bs"]))
    if shares <= 0:
        result["scenario"] = "ZERO_LIQUIDITY"
        return result
    scenarios = []
    for bps in SIDE_COST_BPS:
        gross = shares * (exit_bid - entry_ask)
        fees = shares * (entry_ask + exit_bid) * bps / 10000
        pnl = gross - fees
        scenarios.append({"cost_bps_each_side": bps, "shares": round(shares, 8),
                          "entry_ask": entry_ask, "exit_bid": exit_bid,
                          "gross_usd": round(gross, 6), "fees_usd": round(fees, 6),
                          "net_usd": round(pnl, 6),
                          "hypothetical_wealth_usd": round(INITIAL_WEALTH + pnl, 6),
                          "cash_advantage_usd": round(pnl, 6)})
    result["scenario"] = "FIRST_ELIGIBLE_ASK_TO_LAST_ELIGIBLE_BID_NOT_EXECUTABLE_PROOF"
    result["scenarios"] = scenarios
    return result

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("archive", help="private authenticated HF20 tar.gz archive")
    a = p.parse_args()
    with open(a.archive, "rb") as f:
        print(json.dumps(evaluate(f.read()), sort_keys=True, indent=2))
