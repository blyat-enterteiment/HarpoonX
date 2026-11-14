# C51 observed first-pass diagnostics (independent JS inspection)

- Cohort registered before retrieval: 30 Nasdaq and 10 ARCA ETF symbols, deterministic hash of current listings; **not** historical point-in-time exchange membership.
- 8 Alpaca SIP 5-minute source CSV batches: 37,482 total source bars, 33,828 within regular New York hours in a separate JS audit.
- A 10-prior-session same-time-slot RVOL>5 and completed 5-minute close >10% versus opening, with price < USD5 prior day, yielded **one** preliminary qualifying signal: ECX on 2026-11-12 at 15:50 UTC (10:50 EST), RVOL approximately 7.64.
- In the independent preliminary audit, C49 +5% next-open <= +75bps chase produced **zero** model entries. A *C47-like approximation* yielded one model entry for ECX at USD0.8294. No authenticated fill, no valid N9 alpha.
- CASH benchmark is USD20,000 without interest; ORIGINAL cannot be reconstructed without native original strategy decisions and broker receipts. Do not substitute an invented ORIGINAL result.
- This first-pass inspection is **not** the Python CI final financial result. The complete original C49 pyramid with real NBBO and broker receipts is not reproduced. No point-in-time Finviz population or historical delisted membership.
- NO_GO; zero paper/live orders, zero merges, zero deployments.
