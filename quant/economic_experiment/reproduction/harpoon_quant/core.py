from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.special import ndtr

FEATURES = (
    "momentum_1",
    "momentum_3",
    "momentum_12",
    "rv_12",
    "log_rvol",
    "vwap_z",
    "relative_3",
    "spread_fraction",
)
BOOKS = {"equity", "etf", "crypto", "options", "futures"}
ORIGINS = {"OBSERVED", "SYNTHETIC_ENGINEERING_ONLY"}


def timestamp(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("UTC_OFFSET_REQUIRED")
    return d.astimezone(UTC)


def digest(x: Any) -> str:
    return hashlib.sha256(
        json.dumps(x, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def finite(x: Any, name: str, positive: bool = False) -> float:
    if (
        isinstance(x, bool)
        or not isinstance(x, (int, float))
        or not math.isfinite(x)
        or (positive and x <= 0)
    ):
        raise ValueError("INVALID_" + name)
    return float(x)


@dataclass(frozen=True)
class Config:
    horizon_hours: float = 24
    scenarios: int = 256
    max_positions: int = 4
    gross_fraction: float = 1.0
    asset_fraction: float = 0.35
    factor_fraction: float = 0.60
    cvar_alpha: float = 0.95
    cvar_fraction: float = 0.02
    stress_fraction: float = 0.05
    daily_loss_fraction: float = 0.05
    drawdown_fraction: float = 0.10
    uncertainty_z: float = 2.0
    risk_penalty: float = 0.10
    max_quote_age_seconds: float = 15
    slippage_bps: float = 10
    max_model_age_days: float = 30
    solver_seconds: float = 3
    min_edge_usd: float = 1
    min_robust_return_bps: float = 0
    seed: int = 1701

    def __post_init__(self) -> None:
        for k, v in asdict(self).items():
            finite(v, k)
            if v < 0:
                raise ValueError("NEGATIVE_" + k)
        if not 0 < self.horizon_hours <= 72 or not 0 < self.cvar_alpha < 1:
            raise ValueError("HORIZON_OR_TAIL")
        if self.min_robust_return_bps > 100:
            raise ValueError("QUALITY_BPS_ENVELOPE")
        if not 32 <= self.scenarios <= 4096 or not 1 <= self.max_positions <= 48:
            raise ValueError("COMPUTE_BUDGET")
        if type(self.scenarios) is not int or type(self.max_positions) is not int:
            raise ValueError("INTEGER_CONFIG")
        if (
            min(
                self.cvar_fraction,
                self.stress_fraction,
                self.gross_fraction,
                self.asset_fraction,
                self.factor_fraction,
                self.solver_seconds,
            )
            <= 0
        ):
            raise ValueError("ZERO_BOUND")


def features(
    bars: list[dict[str, Any]],
    quote: dict[str, Any],
    when: str,
    benchmark: list[dict[str, Any]] | None = None,
) -> list[float]:
    """Closed known bars only. Metadata session prevents overnight RV contamination."""
    at = timestamp(when)
    rows = sorted(
        (
            b
            for b in bars
            if timestamp(b["end"]) <= at and timestamp(b["known_at"]) <= at
        ),
        key=lambda b: timestamp(b["end"]),
    )
    if len(rows) < 32:
        raise ValueError("FEATURE_WARMUP_32_BARS")
    if (at - timestamp(rows[-1]["end"])).total_seconds() > 660:
        raise ValueError("STALE_BARS")
    if timestamp(quote["at"]) > at or timestamp(quote["known_at"]) > at:
        raise ValueError("FUTURE_QUOTE")
    closes = np.array([finite(b["close"], "CLOSE", True) for b in rows])
    for b in rows:
        if finite(b["volume"], "VOLUME") < 0:
            raise ValueError("NEGATIVE_VOLUME")
    log = np.log(closes)
    mom = [float(log[-1] - log[-1 - k]) for k in (1, 3, 12)]
    adjacent = [
        math.log(b["close"] / a["close"])
        for a, b in pairwise(rows)
        if a.get("session") == b.get("session")
        and timestamp(a["end"]) == timestamp(b["start"])
    ]
    if len(adjacent) < 12:
        raise ValueError("VOL_WARMUP_12_ADJACENT_RETURNS")
    rv = max(1e-7, float(np.sqrt(np.mean(np.square(adjacent[-12:])))))
    current_session = rows[-1].get("session")
    slot = rows[-1].get("slot", timestamp(rows[-1]["end"]).strftime("%H:%M"))
    current_rows = [b for b in rows if b.get("session") == current_session]
    historical: dict[str, list[dict[str, Any]]] = {}
    for b in rows:
        if (
            b.get("session") != current_session
            and b.get("slot", timestamp(b["end"]).strftime("%H:%M")) <= slot
        ):
            historical.setdefault(b["session"], []).append(b)
    comparable = [
        sum(b["volume"] for b in bs)
        for _, bs in sorted(historical.items())[-20:]
        if len(bs) >= len(current_rows)
    ]
    if len(comparable) < 10 or np.mean(comparable) <= 0:
        raise ValueError("RVOL_10_TIME_COMPARABLE_SESSIONS_REQUIRED")
    rvol = sum(b["volume"] for b in current_rows) / float(np.mean(comparable))
    current = [b for b in rows if b.get("session") == rows[-1].get("session")]
    den = sum(b["volume"] for b in current)
    if den <= 0:
        raise ValueError("ZERO_VOLUME")
    vw = sum(finite(b["vwap"], "VWAP", True) * b["volume"] for b in current) / den
    bid = finite(quote["bid"], "BID", True)
    ask = finite(quote["ask"], "ASK", True)
    if ask < bid:
        raise ValueError("CROSSED_QUOTE")
    market = 0.0
    if benchmark is not None:
        br = sorted(
            (
                b
                for b in benchmark
                if timestamp(b["known_at"]) <= at and timestamp(b["end"]) <= at
            ),
            key=lambda b: timestamp(b["end"]),
        )
        if len(br) < 4 or br[-1]["end"] != rows[-1]["end"]:
            raise ValueError("BENCHMARK_ALIGNMENT")
        market = math.log(br[-1]["close"] / br[-4]["close"])
    # The same vector is used for all books; options forecast the underlying.
    return [
        *mom,
        rv,
        math.log1p(rvol),
        math.log(ask / vw) / rv,
        mom[1] - market,
        (ask - bid) / ask,
    ]


def expected_shortfall(loss: np.ndarray, alpha: float = 0.95) -> float:
    loss = np.asarray(loss, dtype=float)
    if (
        loss.ndim != 1
        or not len(loss)
        or not np.isfinite(loss).all()
        or not 0 < alpha < 1
    ):
        raise ValueError("BAD_ES_INPUT")
    v = np.sort(loss)[::-1]
    mass = (1 - alpha) * len(v)
    whole = math.floor(mass)
    fraction = mass - whole
    return float(
        (v[:whole].sum() + (fraction * v[whole] if whole < len(v) else 0)) / mass
    )


def covariance(panel: np.ndarray, shrink: float = 0.15) -> np.ndarray:
    x = np.asarray(panel, dtype=float)
    if (
        x.ndim != 2
        or x.shape[0] < 2
        or not np.isfinite(x).all()
        or not 0 <= shrink <= 1
    ):
        raise ValueError("BAD_COVARIANCE_PANEL")
    s = np.atleast_2d(np.cov(x, rowvar=False))
    s = (1 - shrink) * s + shrink * np.diag(np.diag(s))
    vals, vecs = np.linalg.eigh(s)
    return (vecs * np.maximum(vals, 1e-12)) @ vecs.T


def option_price(
    spot: np.ndarray,
    strike: float,
    years: float,
    vol: np.ndarray,
    rate: float,
    dividend: float,
    right: str,
    style: str = "european",
) -> np.ndarray:
    spot = np.asarray(spot, dtype=float)
    vol = np.broadcast_to(np.asarray(vol, dtype=float), spot.shape)
    sign = 1 if right == "call" else -1 if right == "put" else 0
    if not sign or strike <= 0 or (spot <= 0).any() or (vol <= 0).any():
        raise ValueError("OPTION_DOMAIN")
    if years <= 0:
        return np.maximum(sign * (spot - strike), 0)
    if style == "american":
        # CRR lattice,128steps. Approximation checked against bounds/parity in tests.
        n = 128
        dt = years / n
        u = np.exp(vol * np.sqrt(dt))
        d = 1 / u
        prob = (np.exp((rate - dividend) * dt) - d) / (u - d)
        if (prob < 0).any() or (prob > 1).any():
            raise ValueError("CRR_PROBABILITY_DOMAIN")
        j = np.arange(n + 1)
        levels = spot[:, None] * u[:, None] ** j * d[:, None] ** (n - j)
        val = np.maximum(sign * (levels - strike), 0)
        for k in range(n - 1, -1, -1):
            val = np.exp(-rate * dt) * (
                prob[:, None] * val[:, 1:] + (1 - prob[:, None]) * val[:, :-1]
            )
            j = np.arange(k + 1)
            under = spot[:, None] * u[:, None] ** j * d[:, None] ** (k - j)
            val = np.maximum(val, np.maximum(sign * (under - strike), 0))
        return val[:, 0]
    if style != "european":
        raise ValueError("OPTION_STYLE")
    root = vol * np.sqrt(years)
    d1 = (np.log(spot / strike) + (rate - dividend + 0.5 * vol**2) * years) / root
    d2 = d1 - root
    return sign * (
        spot * np.exp(-dividend * years) * ndtr(sign * d1)
        - strike * np.exp(-rate * years) * ndtr(sign * d2)
    )


def scenarios(
    calibration: dict[str, Any], forecasts: dict[str, float], cfg: Config
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], int]:
    models = calibration["models"]
    names = sorted(forecasts)
    dates = (
        set.intersection(*(set(models[s]["residuals"]) for s in names))
        if names
        else set()
    )
    ordered = sorted(dates)
    if len(ordered) < 20:
        raise ValueError("JOINT_RESIDUAL_PANEL_20_DATES_REQUIRED")
    panel = np.array(
        [[models[s]["residuals"][d] for s in names] for d in ordered], dtype=float
    )
    if not np.isfinite(panel).all():
        raise ValueError("NONFINITE_RESIDUALS")
    rng = np.random.default_rng(cfg.seed)
    indexes: list[int] = []
    while len(indexes) < cfg.scenarios:
        start = int(rng.integers(len(panel)))
        indexes.extend((start + j) % len(panel) for j in range(5))
    draws = panel[indexes[: cfg.scenarios]]
    # Shared rows preserve cross-asset dependence. Stresses are separate constraints,
    # not assigned invented physical probabilities in the expectation.
    cov = covariance(panel)
    sigma = np.sqrt(np.diag(cov))
    base = {}
    stress = {}
    for j, s in enumerate(names):
        base[s] = np.clip(forecasts[s] + draws[:, j], -0.95, 2)
        if "iv_residuals" in models[s] and all(
            d in models[s]["iv_residuals"] for d in ordered
        ):
            base[s + "::iv"] = np.clip(
                np.array(
                    [
                        models[s]["iv_residuals"][ordered[k]]
                        for k in indexes[: cfg.scenarios]
                    ]
                ),
                -0.8,
                2,
            )
        shock = max(0.10, 3 * float(sigma[j]))
        stress[s] = np.array([-min(0.95, shock), min(2, shock), -min(0.95, 2 * shock)])
    return base, stress, len(ordered)


def pnl_lot(
    c: dict[str, Any],
    returns: np.ndarray,
    cfg: Config,
    *,
    held: bool = False,
    stress: bool = False,
    iv_changes: np.ndarray | None = None,
) -> np.ndarray:
    book = c["book"]
    spot = finite(c["spot"], "SPOT", True)
    qty = finite(c.get("lot_qty", 1), "LOT_QTY", True)
    mult = finite(c.get("multiplier", 1), "MULTIPLIER", True)
    bid = finite(c["bid"], "BID", True)
    ask = finite(c["ask"], "ASK", True)
    if ask < bid:
        raise ValueError("CROSSED_QUOTE")
    entry = bid if held else max(ask, finite(c.get("entry", ask), "ENTRY", True))
    extra = finite(c.get("extra_slippage_bps_per_side", 0), "EXTRA_SLIPPAGE")
    if extra < 0:
        raise ValueError("NEGATIVE_EXTRA_SLIPPAGE")
    slip = cfg.slippage_bps + extra
    exit_friction = (ask - bid) / 2 + bid * slip / 10000
    fee = finite(c.get("fee_per_side_usd", 0), "FEES") * (1 if held else 2)
    if fee < 0:
        raise ValueError("NEGATIVE_FEES")
    if book == "options":
        expiry = timestamp(c["expiry_at"])
        at = timestamp(c["asof"])
        years = (expiry - at).total_seconds() / (365 * 86400)
        if years <= cfg.horizon_hours / (24 * 365) + 1 / 365:
            raise ValueError("OPTION_LIFECYCLE_HORIZON")
        if c.get("lifecycle_reviewed") is not True:
            raise ValueError("OPTION_LIFECYCLE_REVIEW_REQUIRED")
        iv = finite(c["iv"], "IV", True)
        rate = finite(c["rate"], "RATE")
        div = finite(c["dividend_yield"], "DIVIDEND")
        strike = finite(c["strike"], "STRIKE", True)
        style = c.get("style", "american")
        p0 = float(
            option_price(
                np.array([spot]),
                strike,
                years,
                np.array([iv]),
                rate,
                div,
                c["right"],
                style,
            )[0]
        )
        if not stress and iv_changes is None:
            raise ValueError("OPTION_JOINT_IV_CALIBRATION_REQUIRED")
        future_iv = (
            np.full(len(returns), iv) if iv_changes is None else iv * (1 + iv_changes)
        )
        if stress:
            future_iv *= np.array([1.30, 0.70, 1.50])
        terminal = option_price(
            np.maximum(1e-6, spot * (1 + returns)),
            strike,
            years - cfg.horizon_hours / (365 * 24),
            future_iv,
            rate,
            div,
            c["right"],
            style,
        )
        # Anchor valuation to the observed midpoint; do not treat model mispricing as alpha.
        mark = np.maximum(0, (ask + bid) / 2 + terminal - p0 - exit_friction)
    else:
        mark = np.maximum(0, spot * (1 + returns) - exit_friction)
    return qty * mult * (mark - entry - (0 if held else ask * slip / 10000)) - qty * fee


def instrument(c: dict[str, Any], cfg: Config) -> tuple[float, float]:
    book = c["book"]
    q = finite(c.get("lot_qty", 1), "LOT_QTY", True)
    mult = finite(c.get("multiplier", 1), "MULTIPLIER", True)
    step = finite(c.get("step", 1), "STEP", True)
    if abs(q / step - round(q / step)) > 1e-5 * max(1, abs(q / step)):
        raise ValueError("NONOPERABLE_LOT")
    if book in ("equity", "etf", "options", "futures") and (
        q != int(q) or step != int(step)
    ):
        raise ValueError("WHOLE_CONTRACTS_OR_SHARES_REQUIRED")
    if book not in BOOKS:
        raise ValueError("UNKNOWN_BOOK")
    if c.get("side", "long") != "long":
        raise ValueError("SHORT_FINANCING_ADAPTER_REQUIRED")
    notional = q * mult * finite(c["spot"], "SPOT", True)
    if book == "options":
        delta = finite(c["delta"], "DELTA")
        if (
            not -1 <= delta <= 1
            or (c.get("right") == "call" and delta < 0)
            or (c.get("right") == "put" and delta > 0)
        ):
            raise ValueError("DELTA_DOMAIN")
        notional *= abs(delta)
    extra = finite(c.get("extra_slippage_bps_per_side", 0), "EXTRA_SLIPPAGE")
    if extra < 0:
        raise ValueError("NEGATIVE_EXTRA_SLIPPAGE")
    cash = q * mult * float(c.get("entry", c["ask"])) * (
        1 + (cfg.slippage_bps + extra) / 10000
    ) + 2 * q * float(c.get("fee_per_side_usd", 0))
    if book == "futures":
        if c.get("margin_verified") is not True or c.get("roll_reviewed") is not True:
            raise ValueError("FUTURES_MARGIN_AND_ROLL_REQUIRED")
        cash = q * finite(c["initial_margin_usd"], "MARGIN", True) + 2 * q * float(
            c.get("fee_per_side_usd", 0)
        )
    return cash, notional


def predict(
    cal: dict[str, Any], underlying: str, x: list[float], when: str, cfg: Config
) -> float:
    if (
        cal.get("feature_names") != list(FEATURES)
        or float(cal["horizon_hours"]) != cfg.horizon_hours
    ):
        raise ValueError("MODEL_SCHEMA_OR_HORIZON")
    now = timestamp(when)
    fit = timestamp(cal["available_at"])
    if fit >= now or now - fit > timedelta(days=cfg.max_model_age_days):
        raise ValueError("MODEL_AGE_OR_FUTURE")
    m = cal["models"].get(underlying)
    if m is None or m.get("accepted") is not True:
        raise ValueError("NO_CALIBRATED_MODEL:" + underlying)
    values = np.asarray(x, dtype=float)
    means = np.asarray(m["mean"])
    scales = np.asarray(m["scale"])
    beta = np.asarray(m["beta"])
    if (
        values.shape != (len(FEATURES),)
        or not np.isfinite(values).all()
        or (scales <= 0).any()
    ):
        raise ValueError("FEATURE_DOMAIN")
    z = (values - means) / scales
    if np.max(np.abs(z)) > 8:
        raise ValueError("FEATURE_DRIFT")
    return float(np.r_[1, z] @ beta)


def allocate(
    request: dict[str, Any], calibration: dict[str, Any], cfg: Config
) -> dict[str, Any]:
    when = request["asof"]
    now = timestamp(when)
    origin = calibration.get("origin")
    receipt: dict[str, Any] = {
        "engine": "HARPOON_QUANT_1",
        "asof": when,
        "status": "RESEARCH_ONLY",
        "liveApproved": False,
        "execution_allowed": False,
        "selected": [],
        "rejected": {},
        "config_hash": digest(asdict(cfg)),
        "model_hash": digest(calibration),
    }
    if origin not in ORIGINS:
        raise ValueError("EXPLICIT_CALIBRATION_ORIGIN")
    a = request["account"]
    eq = finite(a["equity"], "EQUITY", True)
    cash = finite(a["cash"], "CASH")
    pending = finite(a.get("pending_cash", 0), "PENDING")
    if pending < 0:
        raise ValueError("NEGATIVE_RESERVATION")
    cash = min(cash, finite(a["buying_power"], "BUYING_POWER")) - pending
    daily = finite(a.get("daily_pnl", 0), "DAILY_PNL")
    dd = finite(a.get("drawdown_fraction", 0), "DRAWDOWN")
    if daily <= -eq * cfg.daily_loss_fraction or dd >= cfg.drawdown_fraction:
        return {**receipt, "reason": "ACCOUNT_RISK_PAUSE"}
    candidates = request.get("candidates", [])
    if len(candidates) > 96:
        raise ValueError("CANDIDATE_COMPUTE_CAP_96")
    if len({c["id"] for c in candidates}) != len(candidates):
        raise ValueError("DUPLICATE_CANDIDATE_ID")
    forecasts = {}
    feature_bindings: dict[str, str] = {}
    accepted = []
    held = request.get("holdings", [])
    for c in [*held, *candidates]:
        try:
            if c.get("currency", "USD") != "USD":
                raise ValueError("FX_CONVERSION_REQUIRED")
            if (
                not 0
                <= (now - timestamp(c["quote_at"])).total_seconds()
                <= cfg.max_quote_age_seconds
            ):
                raise ValueError("STALE_QUOTE")
            if timestamp(c["known_at"]) > now:
                raise ValueError("FUTURE_INPUT")
            if c["asof"] != when:
                raise ValueError("COMMON_DECISION_REQUIRED")
            instrument(c, cfg)
            s = c["underlying"]
            mu = predict(calibration, s, c["features"], when, cfg)
            binding = digest(c["features"])
            if s in feature_bindings and feature_bindings[s] != binding:
                raise ValueError("INCONSISTENT_UNDERLYING_FEATURES")
            feature_bindings[s] = binding
            forecasts[s] = mu
            if c in candidates:
                accepted.append(c)
        except (ValueError, KeyError) as exc:
            if c in held:
                return {
                    **receipt,
                    "reason": "UNMODELED_OPEN_INVENTORY",
                    "detail": str(exc),
                }
            receipt["rejected"][c["id"]] = str(exc)
    if not accepted:
        return {**receipt, "reason": "NO_ADMISSIBLE_CALIBRATED_CANDIDATES"}
    base, shock, n_eff = scenarios(calibration, forecasts, cfg)
    # Repricing needs no future prices. Missing calibration for a held name blocks entry.
    existing = np.zeros(cfg.scenarios)
    existing_stress = np.zeros(3)
    existing_gross = 0.0
    existing_factor: dict[str, float] = {}
    for c in held:
        existing += pnl_lot(
            c,
            base[c["underlying"]],
            cfg,
            held=True,
            iv_changes=base.get(c["underlying"] + "::iv"),
        )
        existing_stress += pnl_lot(
            c, shock[c["underlying"]], cfg, held=True, stress=True
        )
        _, gross = instrument(c, cfg)
        existing_gross += gross
        factor = c.get("factor", c["underlying"])
        existing_factor[factor] = existing_factor.get(factor, 0) + gross
    kept = []
    pnl = []
    stress_pnl = []
    fund = []
    exposure = []
    for c in accepted:
        try:
            vals = pnl_lot(
                c,
                base[c["underlying"]],
                cfg,
                iv_changes=base.get(c["underlying"] + "::iv"),
            )
            st = pnl_lot(c, shock[c["underlying"]], cfg, stress=True)
            cost, gross = instrument(c, cfg)
            if not np.isfinite(vals).all() or not np.isfinite(st).all():
                raise ValueError("NONFINITE_VALUATION")
            kept.append(c)
            pnl.append(vals)
            stress_pnl.append(st)
            fund.append(cost)
            exposure.append(gross)
        except (ValueError, KeyError) as exc:
            receipt["rejected"][c["id"]] = str(exc)
    if not kept:
        return {**receipt, "reason": "NO_VALUABLE_CANDIDATES"}
    matrix = np.array(pnl).T
    stress_matrix = np.array(stress_pnl).T
    # Broker fills arrive in stages. Do not spend risk headroom from another
    # proposed leg's gains: these upper bounds cover any subset of new fills.
    risk_matrix = np.minimum(matrix, 0)
    risk_stress_matrix = np.minimum(stress_matrix, 0)
    n = len(kept)
    s = cfg.scenarios
    effective_dates = n_eff / max(5, math.ceil(cfg.horizon_hours / 24))
    uncertainty = (
        cfg.uncertainty_z * np.std(matrix, axis=0, ddof=1) / math.sqrt(effective_dates)
    )
    robust = matrix.mean(axis=0) - uncertainty
    # Lot counts are integers; binary activity handles fixed fees and campaign count.
    width = 2 * n + 1 + s
    objective = np.zeros(width)
    objective[:n] = -robust
    objective[n : 2 * n] = [float(c.get("fixed_fee_usd", 0)) for c in kept]
    objective[2 * n] = cfg.risk_penalty
    objective[2 * n + 1 :] = cfg.risk_penalty / (s * (1 - cfg.cvar_alpha))
    upper = np.full(width, np.inf)
    lower = np.zeros(width)
    lower[2 * n] = -eq * 10
    upper[2 * n] = eq * 10
    maxlots = np.array(
        [
            max(
                0,
                min(
                    math.floor(max(0, cash) / cost),
                    math.floor(eq * cfg.asset_fraction / max(gross, 1e-12)),
                    math.floor(
                        float(c.get("max_qty", 1e9)) / float(c.get("lot_qty", 1))
                    ),
                ),
            )
            if robust[i] > 0 and 10000 * robust[i] / cost >= cfg.min_robust_return_bps
            else 0
            for i, (c, cost, gross) in enumerate(zip(kept, fund, exposure, strict=True))
        ],
        dtype=float,
    )
    upper[:n] = maxlots
    upper[n : 2 * n] = 1
    integral = np.zeros(width)
    integral[: 2 * n] = 1
    rows = []
    ubs = []

    def add(coeff: dict[int, float], bound: float) -> None:
        row = np.zeros(width)
        for j, v in coeff.items():
            row[j] = v
        rows.append(row)
        ubs.append(bound)

    fees = np.array([finite(c.get("fixed_fee_usd", 0), "FIXED_FEE") for c in kept])
    if (fees < 0).any():
        raise ValueError("NEGATIVE_FIXED_FEES")
    add(
        {**{i: v for i, v in enumerate(fund)}, **{n + i: fees[i] for i in range(n)}},
        max(0, cash),
    )
    add(
        {i: v for i, v in enumerate(exposure)}, eq * cfg.gross_fraction - existing_gross
    )
    add({n + i: 1 for i in range(n)}, max(0, cfg.max_positions - len(held)))
    for i in range(n):
        add({i: 1, n + i: -maxlots[i]}, 0)
        add({i: -1, n + i: 1}, 0)
    for symbol in {c["underlying"] for c in kept}:
        add(
            {n + i: 1 for i, c in enumerate(kept) if c["underlying"] == symbol},
            0 if any(h["underlying"] == symbol for h in held) else 1,
        )
    for factor in {c.get("factor", c["underlying"]) for c in kept}:
        add(
            {
                i: exposure[i]
                for i, c in enumerate(kept)
                if c.get("factor", c["underlying"]) == factor
            },
            eq * cfg.factor_fraction - existing_factor.get(factor, 0),
        )
    for k in range(s):
        add(
            {
                **{i: -risk_matrix[k, i] for i in range(n)},
                **{n + i: fees[i] for i in range(n)},
                2 * n: -1,
                2 * n + 1 + k: -1,
            },
            existing[k],
        )
    add(
        {2 * n: 1, **{2 * n + 1 + k: 1 / (s * (1 - cfg.cvar_alpha)) for k in range(s)}},
        min(eq * cfg.cvar_fraction, eq * cfg.daily_loss_fraction + min(0, daily)),
    )
    for k in range(3):
        add(
            {
                **{i: -risk_stress_matrix[k, i] for i in range(n)},
                **{n + i: fees[i] for i in range(n)},
            },
            eq * cfg.stress_fraction + existing_stress[k],
        )
    result = milp(
        objective,
        integrality=integral,
        bounds=Bounds(lower, upper),
        constraints=LinearConstraint(np.array(rows), -np.inf, np.array(ubs)),
        options={
            "time_limit": cfg.solver_seconds,
            "mip_rel_gap": 1e-6,
            "presolve": True,
        },
    )
    if result.status != 0 or result.x is None:
        return {
            **receipt,
            "reason": "SOLVER_NO_OPTIMAL_SOLUTION",
            "solver_status": int(result.status),
        }
    x = np.rint(result.x[:n])
    y = np.rint(result.x[n : 2 * n])
    portfolio = existing + matrix @ x - fees @ y
    stress_total = existing_stress + stress_matrix @ x - fees @ y
    es = expected_shortfall(-portfolio, cfg.cvar_alpha)
    if (
        (np.array(rows) @ result.x - np.array(ubs)).max() > 1e-5
        or np.dot(fund, x) + fees @ y > cash + 1e-5
        or (x < 0).any()
        or not math.isfinite(es)
    ):
        raise ArithmeticError("POST_SOLVER_CONSTRAINT_CHECK")
    robust_value = float(robust @ x - objective[n : 2 * n] @ y)
    if robust_value < cfg.min_edge_usd:
        return {**receipt, "reason": "CASH_DOMINATES_AFTER_UNCERTAINTY"}
    selected = [
        {
            "id": c["id"],
            "symbol": c["symbol"],
            "book": c["book"],
            "quantity": float(x[i] * c.get("lot_qty", 1)),
            "lots": int(x[i]),
            "expected_net_usd": float(matrix[:, i].mean() * x[i] - fees[i] * y[i]),
            "robust_net_usd": float(robust[i] * x[i] - fees[i] * y[i]),
            "cash_committed_usd": float(fund[i] * x[i] + fees[i] * y[i]),
        }
        for i, c in enumerate(kept)
        if x[i] > 0
    ]
    return {
        **receipt,
        "selected": selected,
        "reason": "CONDITIONAL_MODEL_ALLOCATION",
        "execution_allowed": origin == "OBSERVED",
        "expected_net_usd": float(portfolio.mean()),
        "robust_incremental_usd": robust_value,
        "cvar_usd": es,
        "partial_fill_cvar_upper_usd": expected_shortfall(
            -(existing + risk_matrix @ x - fees @ y), cfg.cvar_alpha
        ),
        "stress_worst_loss_usd": float(-stress_total.min()),
        "partial_fill_stress_upper_usd": float(
            -(existing_stress + risk_stress_matrix @ x - fees @ y).min()
        ),
        "cash_committed_usd": float(np.dot(fund, x) + fees @ y),
        "scenario_count": s,
        "joint_residual_dates": n_eff,
        "uncertainty_effective_dates_approx": effective_dates,
        "solver_status": int(result.status),
        "note": "Model outputs with historical residual resampling, not realized returns or independently validated profit.",
    }
