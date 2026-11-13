# HARPOONX N10 — Phase 0: options frontier (engineering only)

## Status and isolation

This branch is derived from immutable **C13 completed** commit `c735cd519a34d3b2104e3a224ba2cc3698f3b8af`, not from concurrently active C14. No N9/M9/M10 file is modified. N9-S remains NO_GO. The original M10 final 3,200 accounts stay sealed; original automation stays disabled; PR #7 remains independent and in draft. No N10 observed profitability is claimed.

**N10 Phase 0** implements a deterministic **read-only** analytical module in `quant/harpoon_quant/n10_options.py`: one-lot European cash-settled CALL/PUT and two-leg debit/credit verticals; market bid/ask and quote sizes; `known_at` checks; projected 48–72h outcome valuation; scenario robust expected log growth; hard funding and risk admission; a CASH fallback. It cannot create, submit or transmit orders. It does not invent actual option chains or fills.

## Architecture and contracts

| Module | Implemented gate | Status |
| --- | --- | --- |
| Contract/Quote | European cash settlement, 100x multiplier, positive strike, valid bilateral bid/ask, bid/ask size >0 | Implemented |
| Scenario | Forecast created by or before decision; positive IV/spot, probabilities total 1 | Implemented |
| Portfolio | Known-at funded cash, equity, prior commitments, high-water and session clock | Implemented |
| Guard | $20,000 starting reference; 0.25% shared risk; 12% commitment at admission; 2% daily stop; 8% DD; 72h | Implemented, Phase0 semantics only |
| Candidate | Long option or covered two-leg, same-expiry vertical; no naked shorts | Implemented |
| evaluate | Entry at observed ASK for buys / BID for sells, fees and slippage; conservative modeled exit spread; Decimal worst expiry loss | Implemented |
| select | Lower finite-scenario expected log via total-variation ambiguity mass; CASH is default | Implemented |
| Historical NBBO and actual option fills | Quote provenance, dynamic sizes, coupled Greek surface, true settlement | **Not implemented** |
| Live market, broker, OMS, autopilot | Orders, API keys, execution, positions | **Prohibited** |
| Independent external review | Native options specialist and audited bookkeeping | **Not completed** |

This is **not** the original M9 risk semantics for share notionals. The N10 options translation reserves the maximum contractual loss or paid debit as *risk capital*, alongside an additional shared 12% admission commitment. 12% is explicitly not a continuously enforced leverage cap; no claims of N9 equivalence or actual option-margin sufficiency are made. 0.25% of $20,000 starts at $50 across all active risk commitments. If one real contract cannot fit this minimum, return CASH; never increase leverage to force an entry.

### Forecast versus execution

The entry side uses supplied bid/ask quotes and a separately specified synthetic fee/slippage contract ($0.65 fee per leg per side, $0.01 premium slippage per leg per side by default; **not** M9 stock costs). The future quote is **NOT observed**: Black–Scholes under each ex-ante projected (S, IV) supplies a theoretical mid, reduced by the input quote's halfspread and slippage to calculate a hypothetical liquidation. This tests the geometry of P-vs-Q preferences; it is **not a backtest, an executable future quote, or real profitability**. Real option NBBO and a joint future skew/term-structure model must be separately implemented and authenticated before any economic result.

### Finite catalogue, controls and falsifiers

The registered six structures are long CALL, long PUT, bull-call-debit, bear-put-debit, bull-put-credit and bear-call-credit verticals. Controls: CASH, P=Q placebo, sign-permuted forecast, risk-matched underlying (only if truly comparable), previous best (only if transferable without remapping source histories). No regime oracle may receive future prices or be promoted.

Falsifiers: accepting a quote/label/portfolio from the future, stale/crossed markets, uncollateralized short, over-budget one-lot position, releasing shared reservations, trading a non-positive robust forecast advantage, a 73h hold, or a non-positive cash ledger. All observed fixtures and code changes must retain a provenance hash. Positive invented forecasts are **tests**, not economic evidence.

## Integration roadmap / acceptance ladder

**P0 — engineering** (this unit): pure deterministic pricer/strategy assessor, independent Decimal max-loss checks, timing/risk tests, microbenchmark, static/type CI and source hashes. 0 statistical accounts, no OOS/market data.

**P1 — authenticated option data**: real synchronized NBBO/size and underlying knownAt, unique instrument identifiers and expiration type, rates and corporate actions when relevant, executable debit/credit packets, broad stale/fault matrix. Obtain data only from licensed/authorized sources; no hidden API accesses.

**P2 — predictive evidence**: separate, preregistered P-model forecasts vs observed option Q-prices, blocked/purged chronological folds, embargo at least forecast horizon, no feature look-ahead. Reserve null worlds and a P=Q control. Limit 18 candidates, 5 controls, 5,040 funded path accounts and 4 workers. Record attempts including failures. **Never** reuse M10 final holdouts or optimize on a viewed N10 holdout.

**P3 — independently auditable execution**: complete package bid/ask, partials/rejects/outages/market impact, discontinuous skew, settlement at expiry, clock convergence, capital coordinator among assets and derivative underlyings, reconciliation independently from decision engine, persistent receipts. The original two operational omissions remain blocking.

**P4 — internal conditional N10 gate, not N9**: preregister an options-specific net log growth hurdle before outcome inspection, baseline CASH and risk-matched alternatives on identical time paths, fees, worst-session, event DD, best-campaign exclusion, stability across worlds, prospective multiplicity budget, independent external-style accounting. No retroactive alpha coverage. No declaration of real profitability; no broker or deployment without a separate explicit authorization.

## Running the implemented module

From repository root:

    PYTHONPATH=. python -m unittest discover -s tests -p test_n10_options.py -v
    PYTHONPATH=. python tools/n10_phase0_verify.py
    python -m compileall -q quant/harpoon_quant/n10_options.py

The module has no external runtime dependencies. Supply Quote, Scenario and Portfolio objects to select. It **returns an analytical label plus audit records only**, never an order or position. Guard refuses any changed original numeric capital/risk/horizon settings in P0. Do not interpret the positive CHEAP_CALL fixture as a return estimate.

## Source references

- Cboe XSP specification (European-style, cash settlement, 100 multiplier): https://www.cboe.com/tradable-products/sp-500/xsp-options/specifications
- Original HarpoonX contract: research/modulation9/protocol.json (unchanged).
- Frozen continuous N9 checkpoint: research/continuous_n9/state.json at C13 parent commit (unchanged).
- N10 preregistration: research/n10/phase0_protocol.json and research/n10/state.json on this branch.
