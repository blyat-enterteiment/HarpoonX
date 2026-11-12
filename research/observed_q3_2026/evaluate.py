"""C37: research-only Q3-2026 historical Alpaca daily-bar economic replay.

Historical observed market bars are real provider-supplied market data,
but ALL entry/exit fills below are modeled (not broker-observed).
No ML fit, no proprietary C22 generator, no real prospective experiment.
The September split was selected AFTER the quarter ended: pseudo-OOS only.
No authorization to trade or to certify N9-S profitability.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import fmean, stdev
from zoneinfo import ZoneInfo

DATA_DIR = Path(__file__).resolve().parent
INPUT = DATA_DIR / "source_manifest.json"
SEPT = date(2026, 9, 1)
OCT = date(2026, 10, 1)
INITIAL = 20_000.0
STRATEGIES = ("breakout10", "momentum5", "reversal3")
ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    vwap: float


@dataclass(frozen=True)
class Candidate:
    symbol: str
    strategy: str
    factor: str
    book: str
    decision_day: date
    entry_at: datetime
    exit_at: datetime
    entry_open: float
    exit_open: float
    cost_bps: float
    stop_stress_bps: float
    raw_gross_bps: float
    net_bps: float


def _sha_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode()
                        + b"\x00" + raw).hexdigest()


def load_data(manifest_path: Path = INPUT) -> tuple[
    dict[str, list[Bar]], dict[str, object]
]:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != (
        "HARPOON_FWN9_C37_OBSERVED_ALPACA_FREE_MARKET_DATA_MANIFEST_1"
    ):
        raise ValueError("C37_MANIFEST_SOURCE_SCHEMA")
    market: dict[str, list[Bar]] = {}
    audit: list[dict[str, object]] = []
    for item in manifest["files"]:
        declared = str(item["path"])
        expected_prefix = "research/observed_q3_2026/raw/"
        if (not declared.startswith(expected_prefix)
                or "/" in declared[len(expected_prefix):]
                or not declared[len(expected_prefix):].endswith(".csv")):
            raise ValueError("C37_SOURCE_PATH_ESCAPE")
        path = DATA_DIR / "raw" / declared[len(expected_prefix):]
        if not path.resolve().is_relative_to((DATA_DIR / "raw").resolve()):
            raise ValueError("C37_SOURCE_PATH_ESCAPE")
        raw = path.read_bytes()
        if _sha_blob(raw) != item["git_blob_sha"]:
            raise ValueError("C37_SOURCE_GIT_BLOB_CHANGED")
        rows: list[Bar] = []
        for record in csv.DictReader(raw.decode("utf-8").splitlines()):
            dt = datetime.fromisoformat(record["timestamp"])
            if dt.utcoffset() is None:
                raise ValueError("C37_SOURCE_NAIVE_CLOCK")
            day = dt.date()
            op, hi, lo, close = (
                float(record[key]) for key in ("open", "high", "low", "close")
            )
            v, vw = float(record["volume"]), float(record["vwap"])
            trades = int(record["trade_count"])
            if (
                not all(math.isfinite(x) for x in (op, hi, lo, close, v, vw))
                or not (hi >= max(op, close) >= lo > 0)
                or v < 0 or vw <= 0 or trades < 0
                or day < date(2026, 7, 1) or day >= OCT
                or (rows and day <= rows[-1].day)
            ):
                raise ValueError("C37_INVALID_OHLCV_CAUSAL_CALENDAR")
            rows.append(Bar(day, op, hi, lo, close, v, trades, vw))
        symbol = str(item["symbol"])
        if (
            symbol in market
            or len(rows) != item["expected_rows"]
            or rows[0].day != date(2026, 7, 1)
            or rows[-1].day != date(2026, 9, 30)
            or rows[0].day.isoformat() not in item["first_timestamp"]
            or rows[-1].day.isoformat() not in item["last_timestamp"]
        ):
            raise ValueError("C37_SOURCE_COVERAGE_INCOMPLETE")
        if item["feed"] == "us":
            days = [date(2026, 7, 1) + timedelta(days=i) for i in range(92)]
            if [r.day for r in rows] != days:
                raise ValueError("C37_CRYPTO_DAILY_COVERAGE")
        elif item["feed"] == "iex":
            if any(r.day.weekday() > 4 for r in rows):
                raise ValueError("C37_EQUITY_WEEKEND_BAR")
        else:
            raise ValueError("C37_UNKNOWN_DATA_FEED")
        market[symbol] = rows
        audit.append({
            "symbol": symbol, "feed": item["feed"], "bars": len(rows),
            "sha256_raw_csv": hashlib.sha256(raw).hexdigest(),
            "git_blob_sha1_verified": True,
            "first_day": rows[0].day.isoformat(),
            "last_day": rows[-1].day.isoformat(),
            "quarter_close_return_pct":
                100 * (rows[-1].close / rows[0].close - 1),
        })
    return market, {
        "schema": "HARPOON_FWN9_C37_OBSERVED_SOURCE_AUDIT_1",
        "rows": sum(len(x) for x in market.values()),
        "feeds": audit,
        "independent_exchange_signature_verified": False,
        "ipo_dividend_split_adjustment_complete": False,
        "SIP_NBBO_available": False,
        "price_fill_reachability_verified": False,
    }


def market_open(day: date, book: str) -> datetime:
    if book == "crypto":
        return datetime.combine(day, time.min, timezone.utc)
    return datetime.combine(day, time(9, 30), ET).astimezone(timezone.utc)


def assumption_cost(symbol: str, stress: bool = False) -> float:
    """bps per whole roundtrip; all except published crypto fee are modeled.

    Equity: 0 commission, estimated combined spread/impact/slippage 13bps.
    Crypto: taker 25bps EACH side + estimated 50bps friction =100bps.
    Stress: 26bps equities, 170bps crypto (assumptions, not broker receipts).
    """
    if symbol in ("BTC/USD", "ETH/USD"):
        return 170.0 if stress else 100.0
    return 26.0 if stress else 13.0


def group_for(symbol: str) -> str:
    return {
        "SPY": "US_INDEX", "QQQ": "US_INDEX", "NVDA": "SEMICONDUCTORS",
        "BTC/USD": "CRYPTO_BETA", "ETH/USD": "CRYPTO_BETA",
    }[symbol]


def proposals_for(
    symbol: str, bars: list[Bar], *, stress: bool = False,
) -> list[Candidate]:
    book = "crypto" if "/" in symbol else "equity"
    result: list[Candidate] = []
    for i in range(15, len(bars) - 3):
        b, history = bars[i], bars[:i]
        close5 = bars[i - 5].close
        close3 = bars[i - 3].close
        prev_vol = fmean(x.volume for x in bars[i - 10:i])
        if prev_vol <= 0 or close5 <= 0 or close3 <= 0:
            continue
        volume_ratio = b.volume / prev_vol
        returns5 = [bars[j].close / bars[j - 1].close - 1
                    for j in range(i - 4, i + 1)]
        returns15 = [bars[j].close / bars[j - 1].close - 1
                     for j in range(i - 14, i + 1)]
        v5 = (sum(x * x for x in returns5) / len(returns5)) ** 0.5
        v15 = (sum(x * x for x in returns15) / len(returns15)) ** 0.5
        volatility_momentum = v5 / max(v15, 1e-9)
        momentum5 = b.close / close5 - 1
        reversal3 = b.close / close3 - 1
        threshold = .025 if book == "crypto" else .01
        rule = {
            "breakout10": (
                b.close > max(x.high for x in history[-10:])
                and volume_ratio > 1.1 and volatility_momentum >= 0.85
            ),
            "momentum5": (
                momentum5 > threshold
                and volume_ratio > .75 and volatility_momentum >= .8
            ),
            "reversal3": (
                reversal3 < -2 * threshold
                and volume_ratio > .9 and volatility_momentum <= 1.25
            ),
        }
        entry = bars[i + 2]  # full extra daily publication-latency embargo
        exit_bar = bars[i + 3]
        et, xt = market_open(entry.day, book), market_open(exit_bar.day, book)
        if (
            et <= market_open(b.day, book)
            or not 0 < (xt - et).total_seconds() <= 72 * 3600
        ):
            continue
        gross_bps = 10_000 * (exit_bar.open / entry.open - 1)
        cost = assumption_cost(symbol, stress)
        tr14 = fmean(x.high - x.low for x in bars[i - 13:i + 1])
        stop_bps = max(100.0, 2 * tr14 / b.close * 10_000)
        for strat in STRATEGIES:
            if rule[strat]:
                result.append(Candidate(
                    symbol=symbol, strategy=strat, factor=group_for(symbol),
                    book=book, decision_day=b.day, entry_at=et, exit_at=xt,
                    entry_open=entry.open, exit_open=exit_bar.open,
                    cost_bps=cost, stop_stress_bps=stop_bps,
                    raw_gross_bps=gross_bps, net_bps=gross_bps - cost,
                ))
    return result


def calibrated(
    all_candidates: list[Candidate],
) -> dict[str, dict[str, float | int | bool]]:
    """Fit ONLY from July/August matured trading observations."""
    by: dict[str, list[Candidate]] = {}
    for x in all_candidates:
        if x.decision_day < SEPT and x.exit_at.date() < SEPT:
            by.setdefault(x.symbol + "|" + x.strategy, []).append(x)
    out: dict[str, dict[str, float | int | bool]] = {}
    for key in sorted(by):
        xs = by[key]
        n = len(xs)
        avg = fmean(x.net_bps for x in xs)
        uncertainty = stdev(x.net_bps for x in xs) if n > 1 else 0.0
        # Conservative only as a heuristic: overlapping market regimes and
        # common price factors prohibit interpreting this as statistical CI.
        effective = max(1, n // 2)
        lower = avg - 2.5 * uncertainty / math.sqrt(effective)
        out[key] = {
            "train_events": n, "mean_net_bps": avg,
            "train_std_net_bps": uncertainty,
            "effective_n_heuristic": effective,
            "lower_score_bps_NOT_confidence_bound": lower,
            "soft_pass": n >= 3 and avg > 0,
            "strict_pass": n >= 4 and lower > 0,
        }
    return out


def simulate_one_book(
    eligible: list[Candidate], priority: dict[str, float],
) -> dict[str, object]:
    """Event driven NEXT-OPEN idealized fill replay, NOT real broker fills."""
    eligible = [x for x in eligible if
                x.decision_day >= SEPT and
                SEPT <= x.entry_at.date() < OCT and
                SEPT <= x.exit_at.date() < OCT]
    eligible.sort(key=lambda x: (
        x.entry_at, -priority.get(x.symbol + "|" + x.strategy, 0),
        x.symbol, x.strategy,
    ))
    NAV = INITIAL
    peak = INITIAL
    dd_max = 0.0
    opens: list[tuple[Candidate, float, float]] = []
    closed: list[dict[str, object]] = []
    rejects: dict[str, int] = {}
    traded = 0.0
    total_fees_cost = 0.0
    final_exit_time = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def reject(reason: str) -> None:
        rejects[reason] = rejects.get(reason, 0) + 1

    def close_through(clock: datetime) -> None:
        nonlocal NAV, peak, dd_max, total_fees_cost
        due = [x for x in opens if x[0].exit_at <= clock]
        for row, notional, risk in sorted(due, key=lambda y: y[0].exit_at):
            pnl = notional * row.net_bps / 10_000
            total_fees_cost += notional * row.cost_bps / 10_000
            NAV += pnl
            peak = max(NAV, peak)
            dd_max = max(dd_max, 1 - NAV / peak)
            closed.append({
                "symbol": row.symbol, "strategy": row.strategy,
                "signal_day": row.decision_day.isoformat(),
                "entry": row.entry_at.isoformat(), "exit": row.exit_at.isoformat(),
                "hold_hours": (row.exit_at - row.entry_at).total_seconds() / 3600,
                "position_usd": notional, "gross_bps": row.raw_gross_bps,
                "cost_assumed_bps": row.cost_bps, "net_pnl_usd": pnl,
                "wealth_after": NAV, "risk_reservation_usd": risk,
                "actual_broker_fill": False,
            })
            opens.remove((row, notional, risk))

    for row in eligible:
        close_through(row.entry_at)
        if any(x[0].symbol == row.symbol or
               x[0].factor == row.factor for x in opens):
            reject("DUPLICATE_ASSET_OR_CORRELATED_FACTOR")
            continue
        base = min(NAV, INITIAL)
        gross_used = sum(x[1] for x in opens)
        risk_used = sum(x[2] for x in opens)
        if NAV <= 0 or base <= 0:
            reject("FINANCIAL_HALT")
            continue
        notional = min(
            0.04 * base,
            max(0, 0.12 * base - gross_used),
            max(0, 0.0025 * base - risk_used)
            * 10_000 / row.stop_stress_bps,
            max(0, NAV - gross_used),
        )
        notional = math.floor(notional * 100) / 100
        if notional < 1.0:
            reject("RISK_OR_SHARED_CASH_EXHAUSTED")
            continue
        risk = notional * row.stop_stress_bps / 10_000
        if gross_used + notional > .12 * base + 1e-9:
            raise AssertionError("C37_GROSS_ADMISSION_BREACH")
        if risk_used + risk > .0025 * base + 1e-9:
            raise AssertionError("C37_RISK_ADMISSION_BREACH")
        opens.append((row, notional, risk))
        traded += notional
    close_through(final_exit_time)
    if opens:
        raise AssertionError("C37_UNCLOSED_72H_OR_QUARTER_POSITION")
    log_per_day = 10_000 * math.log(NAV / INITIAL) / 30
    return {
        "wealth_initial_usd": INITIAL,
        "wealth_terminal_usd": round(NAV, 6),
        "modeled_net_pnl_usd": round(NAV - INITIAL, 6),
        "modeled_net_return_pct": round(100 * (NAV / INITIAL - 1), 6),
        "net_log_growth_bps_per_september_calendar_day": round(log_per_day, 6),
        "closed_modeled_trades": len(closed),
        "gross_nominal_traded_usd": round(traded, 2),
        "estimated_roundtrip_costs_usd": round(total_fees_cost, 6),
        "drawdown_from_event_exit_marks_ONLY_pct": round(100 * dd_max, 6),
        "skipped_due_to_constraints": rejects,
        "trades": closed,
        "actual_alpaca_fills": 0,
        "real_compounding_certified": False,
        "N9S": "NO_GO",
    }


def evaluate() -> dict[str, object]:
    market, source = load_data()
    base_events = [
        x for symbol, rows in market.items()
        for x in proposals_for(symbol, rows)
    ]
    stress_events = [
        x for symbol, rows in market.items()
        for x in proposals_for(symbol, rows, stress=True)
    ]
    train = calibrated(base_events)
    stress_train = calibrated(stress_events)

    def selected(
        rows: list[Candidate],
        calibration: dict[str, dict[str, float | int | bool]],
        gate: str,
    ) -> list[Candidate]:
        selected_pair = {}
        for symbol in market:
            viable = [(key, d) for key, d in calibration.items()
                      if key.startswith(symbol + "|") and bool(d[gate])]
            if viable:
                best = max(viable, key=lambda v: (
                    float(v[1]["lower_score_bps_NOT_confidence_bound"])
                    if gate == "strict_pass" else float(v[1]["mean_net_bps"]),
                    v[0],
                ))
                selected_pair[symbol] = best[0]
        return [x for x in rows if
                x.symbol in selected_pair and
                x.symbol + "|" + x.strategy == selected_pair[x.symbol]]

    def priority(table: dict[str, dict[str, float | int | bool]],
                 metric: str) -> dict[str, float]:
        return {k: float(v[metric]) for k, v in table.items()}

    # The raw momentum comparator is NOT the original HARPOON strategy;
    # it is used as a naive technical reference only.
    benchmark = simulate_one_book(
        [x for x in base_events if x.strategy == "momentum5"], {})
    strict_base = simulate_one_book(
        selected(base_events, train, "strict_pass"),
        priority(train, "lower_score_bps_NOT_confidence_bound"))
    soft_base = simulate_one_book(
        selected(base_events, train, "soft_pass"),
        priority(train, "mean_net_bps"))
    strict_stress = simulate_one_book(
        selected(stress_events, stress_train, "strict_pass"),
        priority(stress_train, "lower_score_bps_NOT_confidence_bound"))
    return {
        "schema": "HARPOON_FWN9_C37_OBSERVED_Q3_HISTORICAL_MODELLED_ECONOMICS_1",
        "source": source,
        "quarter": {"start": "2026-07-01", "end": "2026-09-30",
                    "calibration_end": "2026-08-31",
                    "retrospective_test_month": "2026-09"},
        "strategy_families": list(STRATEGIES),
        "training": train,
        "training_stress": stress_train,
        "candidate_counts": {
            "all_history": len(base_events),
            "historical_calibration": sum(x.decision_day < SEPT
                                           for x in base_events),
            "september_signals": sum(x.decision_day >= SEPT
                                      for x in base_events),
        },
        "cost_assumptions_bps": {
            "equities_base": 13, "equities_stress": 26,
            "crypto_base": 100, "crypto_stress": 170,
            "crypto_real_published_taker_fee_each_side": 25,
            "spread_slippage_impact_actual_receipts": False,
        },
        "modelled_wealth": {
            "cash_zero_yield": {
                "wealth_terminal_usd": INITIAL, "net_log_growth_bps_per_day": 0,
            },
            "naive_momentum_reference_NOT_ORIGINAL": benchmark,
            "incubator_soft_heuristic": soft_base,
            "incubator_strict_heuristic": strict_base,
            "incubator_strict_cost_stress": strict_stress,
        },
        "economic_conclusions": {
            "all_outcomes_are_retrospective": True,
            "calibration_split_pre_registered_before_2026_Q3": False,
            "september_is_not_genuine_prospective_data": True,
            "actual_broker_entry_exit_orders_fills": 0,
            "broker_costs_actually_reconciled": False,
            "original_C22_policy_comparison_available": False,
            "real_prospective_N9_alpha_proven": False,
            "firm_level_growth_target_N9": "NO_GO",
            "M10_holdout_accounts_untouched": 3200,
        },
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2, sort_keys=True))
