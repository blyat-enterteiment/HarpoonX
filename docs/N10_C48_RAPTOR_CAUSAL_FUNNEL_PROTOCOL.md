# HarpoonX — C48 causal funnel (historical diagnostics, NO_GO)

**Parent:** C47 PR #42. This isolated research branch intentionally does NOT
alter C46/C47 rules, M9/M10/M11 results, portfolio accounting or actual
trading permissions. Target PR base: research/m11-c47-raptor-sip-fishing-net.

## Frozen observations

The 16 visible Finviz Raptor names were selected **after** the outcomes
were known. Alpaca SIP supplied 2,540 consolidated 5-minute trade bars,
1,867 regular-session bars across November 12-13, 2026. In C47, historical
HIGH touches were +3%: 8 names and +4%: 6 names. C47 strictly admitted
zero +3% entries and only ENGN +4%; its 100bp roundtrip hypothetical
net result was -USD 24.736402. None of these were authentic broker fills.

The frozen SIP source SHA-256 is
74a1230b581a9654f27f47b624fac2f873add59a76046764e3d045304d6de3a4.

## What C48 now computes

For each symbol at each of the **same two frozen thresholds**:

1. Source eligibility: >=6 previous-session observed regular-hours bars
   and >=3 current-session observed regular-hours bars.
2. Descriptive historical HIGH touch, which NEVER counts as a fill.
3. Two consecutive fully completed five-minute closes >= threshold
   (strict time adjacency and known-at clock).
4. A contiguous following five-minute open before 15:00 New York.
5. The following observed open inside the original +75bp price-chase bound.
6. Cross-check against exact existing C47 state-machine admission.
7. Preserve C47's original hypothetical 100/300/500bp financial
   outcomes WITHOUT recalculating a more favorable fill.

Stages 1-5 form **necessary but insufficient** conditions; counts are
nonexclusive and are not a claim about real executable opportunities.
An observed next OPEN is a zero-latency proxy, not authenticated NBBO,
an electing trade, or a receipt. Missing bars fail closed.

## Operational validation

The included GitHub Actions job compiles the source, runs Ruff/mypy,
executes 10 new timing, gap, non-fill and threshold-unit checks,
re-runs all 12 C47 regressions, pins the SIP source SHA-256, executes
the complete historical causal-funnel report, checks C47 entry equality
and forces NO_GO/no orders. Its artifact is versioned JSON with source hash
and independent report SHA-256.

This experiment makes no claim of a new prospective sample, real Raptor
membership, decision-time RVOL>5, historical NBBO, 72-hour completed
campaigns, real stop fills or an N9 economic edge.

## Next independent evaluation gate (NOT started)

Before viewing fresh performance, register full screener membership and
complete rejection lists. Capture synchronized SIP and NBBO, same-time-of-day
RVOL, quote age and size, order-intent timestamps and independently
authenticated PAPER broker receipts. Only then measure a complete 72h
financed portfolio comparison versus CASH and ORIGINAL, including embargo,
costs, slippage and multiplicity. No use of C46-C48 winners to choose
different triggers or risk limits.

**N9-S NO_GO, N10 NO_GO; M10's 3,200 final accounts stay sealed.
No PAPER/LIVE orders, deployments or merges.**
