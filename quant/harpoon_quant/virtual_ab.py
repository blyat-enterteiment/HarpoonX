"""Continuous cash replay of the actual virtual planner plus frozen A/B overlays."""

from datetime import timedelta

from .virtual_net import plan


def replay(hourly, daily, policy, stress=False, purged=False):
    if policy not in {"CURRENT", "A", "B"}:
        raise ValueError("POLICY")
    rate = (70 if stress else 35) / 10000
    fixed = 2 if stress else 1
    indexed = {s: {b["at"]: b for b in rows} for s, rows in hourly.items()}
    times = sorted(set.intersection(*(set(rows) for rows in indexed.values())))
    cash = 20000.0
    positions = {}
    events = []
    curve = []
    decisions = []
    day = None
    peak = 20000.0
    dd = 0.0

    def sell(s, t, price, reason):
        nonlocal cash
        pos = positions.pop(s)
        value = pos["qty"] * price
        cost = value * rate
        cash += value - cost
        events.append(
            dict(
                at=t.isoformat(),
                symbol=s,
                side="sell",
                qty=pos["qty"],
                price=price,
                cost=cost,
                reason=reason,
            )
        )

    for t in times:
        if t.date() != day:
            cash -= fixed
            day = t.date()
            events.append(dict(at=t.isoformat(), side="fixed", cost=fixed))
        # Opening gaps and deadlines precede new entries. Existing campaign age
        # never resets when B adds another tranche.
        exited = set()
        for s, pos in list(positions.items()):
            b = indexed[s][t]
            if t >= pos["deadline"] or b["open"] <= pos["stop"]:
                sell(s, t, b["open"], "DEADLINE_OR_GAP")
                exited.add(s)
        marks = {s: indexed[s][t]["open"] for s in indexed}
        equity = cash + sum(p["qty"] * marks[s] for s, p in positions.items())
        gross = sum(p["qty"] * marks[s] for s, p in positions.items())
        risk = sum(
            p["qty"] * (max(0, marks[s] - p["stop"]) + 2 * rate * marks[s])
            for s, p in positions.items()
        )
        if t.hour == 12 and t + timedelta(hours=72) <= times[-1] and equity > 0:
            cells = []
            for s in sorted(indexed):
                prior = [b for b in daily[s] if b["known"] < t]
                if len(prior) < 94 or s in exited:
                    continue
                closes = [b["close"] for b in prior]
                if closes[-1] <= sum(closes[-20:]) / 20:
                    continue
                fold_start = t.replace(
                    month=1 + 3 * ((t.month - 1) // 3),
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                cutoff = fold_start - timedelta(hours=72) if purged else t
                training = [b for b in prior if b["known"] < cutoff]
                if len(training) < 91:
                    continue
                history = [b["close"] for b in training]
                labels = [
                    history[i] / history[i - 3] - 1
                    for i in range(len(history) - 1, 2, -3)
                ][:30][::-1]
                if len(labels) < 30 or any(not -1 <= r <= 1 for r in labels):
                    continue
                cells.append(
                    dict(
                        id=s,
                        symbol=s,
                        created_at=t.isoformat(),
                        expires_at=(t + timedelta(seconds=60)).isoformat(),
                        quote_at=t.isoformat(),
                        target_notional=equity * 0.06,
                        stop_fraction=0.02,
                        samples=labels,
                        labels_available_at=training[-1]["known"].isoformat(),
                    )
                )
            packet = dict(
                asof=t.isoformat(),
                cash_available=max(0, cash),
                gross_available=max(0, equity * 0.12 - gross),
                risk_available=max(0, equity * 0.0025 - risk),
                cells=cells,
                positions={s: p["qty"] * marks[s] for s, p in positions.items()},
                pending={},
                costs=dict(
                    fee_bps=rate * 10000, roundtrip_friction_bps=0, fixed_per_order=0
                ),
                seed=17,
            )
            decision = plan(packet)
            decisions.append(
                dict(
                    at=t.isoformat(),
                    max_label_available=max(
                        (c["labels_available_at"] for c in cells), default=None
                    ),
                    cells=len(cells),
                    proposals=len(decision["proposals"]),
                )
            )
            for proposal in decision["proposals"]:
                s = proposal["symbol"]
                amount = proposal["buy_notional"]
                if policy != "CURRENT" and amount < equity * 0.005:
                    continue
                if policy == "B":
                    amount *= 0.5
                price = marks[s]
                stop = positions[s]["stop"] if s in positions else price * 0.98
                # Rerun shared constraints after overlay; an old stop can be
                # farther away than the planner's nominal 2% stop.
                gross = sum(p["qty"] * marks[z] for z, p in positions.items())
                risk = sum(
                    p["qty"] * (max(0, marks[z] - p["stop"]) + 2 * rate * marks[z])
                    for z, p in positions.items()
                )
                amount = min(
                    amount,
                    max(0, cash) / (1 + rate),
                    max(0, equity * 0.12 - gross),
                    max(0, equity * 0.0025 - risk)
                    / (max(0, price - stop) / price + 2 * rate),
                )
                if amount < 1:
                    continue
                qty = amount / price
                cash -= amount * (1 + rate)
                if s in positions:
                    positions[s]["qty"] += qty
                else:
                    positions[s] = dict(
                        qty=qty, stop=stop, deadline=t + timedelta(hours=72)
                    )
                events.append(
                    dict(
                        at=t.isoformat(),
                        symbol=s,
                        side="buy",
                        qty=qty,
                        price=price,
                        cost=amount * rate,
                        deadline=positions[s]["deadline"].isoformat(),
                    )
                )
        # Conservative same-bar stop processing, including new purchases.
        for s, pos in list(positions.items()):
            if indexed[s][t]["low"] <= pos["stop"]:
                sell(s, t, pos["stop"], "STOP")
        nav = cash + sum(
            p["qty"] * indexed[s][t]["close"] for s, p in positions.items()
        )
        peak = max(peak, nav)
        dd = max(dd, 1 - nav / peak)
        curve.append(dict(at=t.isoformat(), equity=nav, cash=cash))
    for s in list(positions):
        sell(s, times[-1], indexed[s][times[-1]]["close"], "END")
    if curve:
        curve[-1].update(equity=cash, cash=cash)
    dd = max(dd, 1 - cash / peak)
    return dict(
        policy=policy,
        stress=stress,
        initial=20000,
        final=cash,
        net=cash - 20000,
        drawdown=dd,
        events=events,
        curve=curve,
        decisions=decisions,
        execution_allowed=False,
    )
