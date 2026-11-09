# M11 P9M-B: signed offline source evidence and causal daily marking

Preregistered structural unit: source authenticity, complete weekday opportunity coverage, per-calendar-day mark-to-market and reconciliation. A canonical Ed25519-signed envelope binds the complete tape, label tape, marks and opportunity records to a key ID. The public key must be provided from an external trust registry; no key is taken from the issuer packet. An issuer can still sign false data, therefore a successful signature is NOT independent corroboration of real fills, quotes or complete source coverage.

Two synthetic equity symbols receive exact daily marks for all 180 dates (carry-forward on weekends) and opportunity records on every trading weekday, including NO_SIGNAL rows. Causal known_at clocks, signal IDs, residual inventory, fees and USD1 cost for every calendar day enter an independent Decimal reconstruction of equity, drawdown and worst trading day. CASH uses the same fixed cost. The best historical policy cannot be paired with this constructed fixture and is not claimed to be validated.

The included deterministic test-only private key is not an external attestation, and the fixture is engineering evidence, not market data. The return remains optimizer_eligible=false, execution_allowed=false, n9s_certified=false. No native M9 OHLC equivalence, real provenance, complete live operational model or production multicell coordinator is claimed. The 12% is admission/reservation, not a continuously enforced cap. No new economic trials, final seeds, or alpha expenditure occurred.

Reproduce: PYTHONPATH=quant python3 -m unittest quant.tests.test_fwn9_source_panel -v after installing the declared Python package dependencies and cryptography. Source paths are new; registered M9/M10 files remain untouched.


## Verified closure (2026-11-08 UTC)

The exact P9M-B CI run 42464439001 passed 12/12 tests, Ruff E4/E7/E9/F, mypy, Python syntax, and printed SHA-256 source/test checksums. Benchmark: 50 full panel audits in 612.408 ms in GitHub Actions Python 3.12. Current-head quant regression on the same unchanged source passed 1,087 tests and 12 reconstructed archive tests (run 42464304235); earlier mypy failures 42464106131 and 42464205064 were retained and corrected under separately versioned protocols.

Fixture (not measured profitability): 180 calendar days, 360 two-symbol marks, 256 weekday opportunities, 1 synthetic signed source, USD 20,000 initial. Cumulative USD 1/calendar-day cost = USD 180. CASH ends at USD 19,820. Receipt fixture ends at USD 19,861.90 after costs, so its arithmetic delta to capital is -USD 138.10. Its +USD 41.90 versus CASH has zero causal market validation and is **not** economic evidence. There was no independent public-key ownership attestation, source authenticity review, opportunity feed coverage verification, full M9 comparability or stochastic N9-S proof. No prior M9/M10 source or recorded result was modified. Full evidence is in evidence/modulation11/fwn9_phase9m_b.json.
