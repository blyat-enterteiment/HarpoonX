PAIRED REPLAY: C0, RIDGE AND SVR

Scope
-----
This executable resource compares the real numerical allocator under a shared
time/invalidation exit policy, an explicit next-quote IOC capacity model and
three continuously funded virtual accounts. It does not reproduce every entry,
trailing, partial-profit or exit plugin of the live coordinator. It cannot claim
full-engine policy parity, place orders or promote the SVR model.
Its instrument adapter is limited to unleveraged equities/ETFs with whole
shares. Leveraged exposure requires a different risk adapter and is rejected;
the replay does not multiply an ETF's quoted price return by its leverage.

The supplied synthetic_request.json and synthetic_result.json are engineering
fixtures. They use artificial market values and a synthetic fitted SVR. They
are not observed trading performance, evidence of alpha, or a recommended
configuration. Repeating the fixture does not add market evidence.

Run from the quant directory
---------------------------
python -m harpoon_quant.paired_replay --input examples/paired_replay/synthetic_request.json --output /tmp/paired-result.json
python -m harpoon_quant.paired_replay --input examples/paired_replay/synthetic_request.json --output /tmp/paired-readiness.json --check-only

The existing NumPy/SciPy dependencies are used. No network, credentials or broker
adapter is present. Scalar SVR training uses the existing scikit-learn dependency;
the replay itself consumes saved JSON models and performs no training.

Required input contracts
------------------------
schema: HARPOON_PAIRED_REPLAY_1
mode: REPLAY
origin: OBSERVED or SYNTHETIC_ENGINEERING_ONLY
initial_cash_usd: finite positive amount
initial_positions: explicit list, including [] when none exist
assets: classified equity/ETF metadata with factor, leverage, multiplier,
        step, minQty and tick; leverage, multiplier, step and minQty must be 1
models: RIDGE and SVR lists of saved artifacts, each with available_at;
        schema and model_kind must match the slot and every internal model;
        legacy Ridge may omit model_kind; SVR requires explicit SVR_RBF
config: the ordinary numerical Config; forecast horizon is unchanged
policy: holding_hours in (0,72], entry_cutoff_minutes at least 10,
        optional policy_id and compute_budget_seconds in (0,600]
costs: explicit per_share_usd, per_order_usd, slippage_bps, verified and reference
provenance: price_origin, execution_origin=MODELED, availability and universe
frames: chronological decisions with non-overlapping later execution quotes

Each frame has decision_id, at, session, calendar open/close, opportunities,
decision quotes, execution quotes, external_flow_before_usd,
operating_costs_usd for C0/RIDGE/SVR, and invalidate_symbols.
Each opportunity has id, symbol, eight canonical features, features_known_at
and max_qty. Each execution quote requires explicit bid_size and ask_size.
An absent or zero capacity does not imply a full fill. Bid/ask reconstructed
from bars must be declared modelled, never labelled observed L1 quotations.

Unknown numerical costs must remain null. The readiness check then reports
MEDICION_BLOQUEADA and returns no profit metrics. Explicit hypothetical numbers
may be used with verified=false; their outputs remain conditional diagnostics.
Operating expenses for gaps between frames must be supplied explicitly; the
replay does not invent infrastructure charges, taxes or income on cash.

Clock and accounting
--------------------
Model availability and feature availability precede each decision. The allocator
receives only the decision snapshot; the later execution quote is not present
in its request. Execution exactly at the closing timestamp is not assumed to
have access to the closing auction. The ten-minute entry cutoff is preserved.

External capital flows occur at the decision instant. Inventory is marked just
before the flow, so a deposit cannot dilute a price gain already accrued since
the preceding execution mark. With E_previous, E_pre_flow, F and E_end:

1 + r = (E_pre_flow / E_previous) * (E_end / (E_pre_flow + F))

Operating costs are expenses inside E_end, not neutralized capital flows.
Execution fees are charged once. Spread and adverse tick-rounded slippage are
already in fill prices and are not debited again. Net dollar PnL is ending NAV
minus starting NAV minus net external capital flows.

Margin borrowing is outside this replay's scope. A withdrawal, expense or exit
fee that creates negative cash while NAV remains positive blocks measurement.
The cash event, negative balance, residual inventory and financing incident
remain in partial_traces; no balancing deposit or liquidation is invented.
Actual insolvency remains recorded under the separate insolvency rule below.

Every output includes an independent event reducer which reconciles cash,
inventory, pre-flow valuation, fees and final marked NAV. This proves internal
consistency, not authenticity of broker executions. Remaining inventory is
marked at the last supplied bid; there is no fabricated terminal liquidation.
Insolvency is retained even if a later deposit or price recovery restores NAV.
An execution gap past 72 hours is recorded as an incident rather than an
imaginary timely exit.

Comparison and statistical limits
---------------------------------
All policies see the same ex-ante opportunity list and universe hash. A model's
absence, rejection or abstention remains in its trace; the universe is not
filtered retrospectively to symbols that both models accepted. Multiple
decisions per session are retained by decision_id. Their returns are combined
into the joint daily portfolio before reporting a paired log-growth difference.
Model availability timestamps are compared as normalized UTC instants: two
text representations of the same instant cannot create competing versions.

Financial acceptance is always false in this resource. An uncertainty interval
is null while block length, search correction and minimum economic effect have
not been preregistered and evaluated. The replay is an accounting/execution
resource for the next economic study, not an automatic financial approval gate.
policy_parity_verified=true is rejected because full-coordinator parity is not
implemented here.

The calibration_readiness(data, available_at, Config) function calls the actual
SVR panel validator without fitting. Calibration remains one row per asset and
session and requires at least 100 distinct sessions. A decision-level training
panel requires a separately versioned residual/dependence contract; duplicate
intraday rows are not silently accepted and cannot overwrite residuals.

Tests
-----
python -m unittest discover -s tests -p test_paired_replay.py -v
python -m unittest discover -s tests -p test_scalar_svr.py -v
python examples/paired_replay/benchmark.py --output /tmp/paired-benchmark.json --runs 30

The targeted tests cover real allocator integration, cash and open losses,
fees, deposits/withdrawals, before-flow price changes, capacity and no fill,
adverse ticks, price gaps and risk bounds, temporal causality, model horizon,
session cutoff, duplicate identities, compute budget, insolvency, ledger
tampering, model-family binding, normalized version timestamps, unsupported
leverage and funding deficits, and multiple intraday decisions without extra
independent sessions.
