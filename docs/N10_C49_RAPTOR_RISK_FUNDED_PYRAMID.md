# C49 — RAPTOR risk-funded 5% breakout pyramid (research-only)

## Chosen hypothesis, not proven alpha

At +5.0% from a known reference, a 5%-NAV requested rung is created.
At +5.5%, +6.0%, etc., subsequent 5%-NAV intents can be created
only if the prior rung is confirmed filled, the quote is causal and
executable, and the risk ledger remains reconciled. A trigger is NOT a fill.

## Mandatory gates

- Shared funded NAV reference USD20,000; no reset between rungs.
- 12% combined gross exposure, 0.25% shared entry risk, 4% research
  idea notional, 72h hard time stop.
- Each rung risks stop distance + full roundtrip cost + stressed gap.
- Do not free risk merely because a trailing stop was ratcheted;
  wait for actual broker receipt and ledger reconciliation.
- Require a calibrated, strictly positive conservative lower net
  expected-edge estimate; without one, admission is rejected.
- Quote and decision timestamps must be causal, quote must be
  executable and within +75bps of rung; no future bar HIGH fills.
- No live/paper order code; every Decision.orders_allowed is false.

## Adversarial confrontation

A naive ladder spends 5% of NAV on each +0.5 percentage-point increase.
At +5% and +5.5%, 10% gross is committed before accounting for
other positions; the third 5% rung violates the 12% global limit.
If a USD1,000 position has a 5% stop distance, the USD50 risk budget
is exhausted even before slippage or fees. Therefore a ladder that
promises two unconditional USD1,000 purchases is not admissible
under M11 controls. C49 instead sizes each rung by remaining funded
risk and leaves the rest in cash.

## Falsification

The kernel verifies *admission safety*, not alpha. The +5% trigger was
chosen after inspecting C46-C48, so reusing those dates as OOS is
prohibited. No improvement to N9 is claimed.

A separate preregistered prospective cohort must record complete
screener membership, rejected candidates, same-time-of-day RVOL,
SIP + synchronized NBBO and actual paper receipts; compare continuous
financed portfolios C49 versus frozen C47, CASH and ORIGINAL over
complete <=72h campaigns, accounting for fees, slippage, partials,
halts, cash reservations, geometric growth, and multiple testing.

**N9-S NO_GO, N10 NO_GO. M10 3,200 sealed finals untouched.
Zero orders, zero deployment, zero merges.**
