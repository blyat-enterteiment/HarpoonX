# HARPOONX FWN9 C23 — observed asset-hour market data and real-execution evidence gate

**Decision: observed market-bar coverage PASS; net executable OOS alpha NOT VERIFIED; optimal trading hour NOT CERTIFIED. N9-S NO_GO.** Six C22 variants remain unexecuted, 3,200 M10 final accounts sealed. No new trading strategy signal, market seed, economic trial account, order, deployment, merge or optimization restart.

## 1. Connected Alpaca market data

Read-only calls to the connected Alpaca market-data connector, with historical period [2026-09-28T00:00:00Z, 2026-11-09T00:00:00Z). This is a **post-view exploratory coverage audit**, not a prospective untouched financial test.

| Symbol | Feed | Sample and completeness |
|---|---|---|
| SPY | IEX, five-minute bars | 30/30 regular exchange sessions, 2,340/2,340 regular bars |
| QQQ | IEX, five-minute bars | 30/30 regular exchange sessions, 2,340/2,340 regular bars |
| BTC/USD | Alpaca US crypto, one-hour bars | 42/42 UTC days, 1,008/1,008 hourly bars |
| ETH/USD | Alpaca US crypto, one-hour bars | 42/42 UTC days, 1,008/1,008 hourly bars |

The crypto endpoint supplied 1,009 records per asset, including an extra bar at the **exclusive** end on November 9, 00:00 UTC. The accepted 1,008 bars use numeric Date.parse milliseconds. A first internal exploratory output incorrectly compared ISO strings with and without fractional seconds, accidentally excluding the first bar while including the end. This error is preserved in commit ba1162dfd461eceb5179b6cd595d93134a8cf663 and corrected in f84061fba77747ce4617c47bdafed02ee572e0e5. Its adversarial CI regression requires the correct 42 complete days.

The feed IEX is not consolidated SIP/NBBO. Alpaca crypto US venue-volume is not equivalent to global BTC/ETH market liquidity. Raw provider market bytes were **not saved/hashed into GitHub**: this summary is a connected read-only source observation, with a reproducible source auditor for any downloaded bytes, not independently source-byte-verified historical data.

## 2. Exploratory hour proxies are not trading returns

| Symbol/window | Mean absolute open-close body (basis points per bar) | Mean source-venue volume per bar |
|---|---:|---:|
| SPY, NY 09:30-10:00 | 7.73849 per five min | 26,417 shares |
| SPY, last 90 min | 3.99290 per five min | 28,517 shares |
| QQQ, NY 09:30-10:00 | 14.65016 per five min | 12,790 shares |
| BTC, 00-08 UTC | 22.24577 per hour | approximately USD 4,615 price*volume |
| BTC, 08-16 UTC (control) | 27.52925 per hour | approximately USD 8,608 price*volume |
| BTC, 16-24 UTC | 20.80761 per hour | approximately USD 6,931 price*volume |
| ETH, 00-08 UTC | 27.96327 per hour | approximately USD 1,294 price*volume |
| ETH, 08-16 UTC (control) | 36.10566 per hour | approximately USD 2,087 price*volume |
| ETH, 16-24 UTC | 29.61342 per hour | approximately USD 1,442 price*volume |

These are **NOT profits, alpha, expected returns, or even executable spreads**. Price*volume per hour is only indicative venue turnover. BTC and ETH show greatest absolute price movement and reported turnover in the 08-16 UTC *negative control* in this sample, challenging earlier intuition behind choosing 00-08 and 16-24 UTC as the two research variants. Do not promote that control retroactively or reuse this already viewed period as an unviewed OOS set.

## 3. Independent public research priors

- Gao, Han, Li and Zhou, Journal of Financial Economics 2018: first-half-hour ETF returns predicted last-half-hour ETF returns in historic 1993-2013 sample. It supports a falsifiable opening/closing hypothesis, not verified 2026 HarpoonX economic performance. DOI https://doi.org/10.1016/j.jfineco.2018.05.009
- Brauneis, Mestel and Theissen, Review of Quantitative Finance and Accounting 2025: 1,940 crypto pairs on 38 exchanges show time-of-day liquidity/volatility patterns; global peak near 16-17 UTC, a different venue and sample from Alpaca US. https://doi.org/10.1007/s11156-024-01304-1
- Bitcoin NY ETF fixing time-of-day study in 2026 finds activity around the NY benchmark and a daylight saving transition but reports hour of day does not predict directional return. https://www.sciencedirect.com/science/article/pii/S1544612326014601

These are priors for research, NOT broker-confirmed profits of the six C22 variants.

## 4. Exact mathematical identification barrier: same OHLC, opposite net fills

A deterministic witness uses ONE bar O=100,H=100.2,L=99.9,C=100.1. A hypothetical ten-share execution buying at 100.02 and selling 100.08 with 0.01 total commission nets +0.59 USD. Another execution buying 100.09 and selling 100.01, with SAME OHLC and commission, nets -0.81 USD. Both hypothetical fill prices lie within the bar range. Neither is an actual broker receipt and the witness does not assert a specific time-ordered tradability path. Therefore observed complete OHLC bars cannot determine realized fill prices, queue effects or net trading profitability. C21 separately disproved universal equality between original OHLC STOP-FIRST and ordered eight-step first-cross execution.

The connected Alpaca tools expose market bars/quotes/trades/options chain snapshots and calendar; they do not expose account-order-fill and fees activity endpoints. The Trading API documents FILL trade activities separately (see https://docs.alpaca.markets/us/docs/account-activities). The account ledger and its credential authorization cannot be inferred from the market-data plugin. The Render connector additionally requires explicit user selection of the workspace before read-only service/log/database exploration.

## 5. Status of original six C22 research variants

| Pre-registered original hypothesis | Usable market clock history | Independently verified broker fills and cash NAV | OOS vs CASH/original certified |
|---|---|---|---|
| H22 opening equity/ETF (two windows) | SPY/QQQ IEX: yes, 30 sessions | NO | NO |
| H22 crypto UTC liquidity (two windows; 08-16 UTC as CONTROL) | BTC/ETH US feed: yes, 42 days | NO | NO |
| H22 put/call option asymmetry (two windows) | Historical matched option OPRA/underlying complete panel NOT available through current connector | NO | NO |

One original account cannot actually run the six unexecuted variants and original baseline simultaneously on the same dollar of capital. Historical quotes can support modeled counterfactuals with error bounds, never be relabeled as actual fills. A truly realized paired comparison requires pre-planned separate budget allocation / randomization with authenticated executions, or clearly differentiated observable original strategy and model controls. Each market day is one dependent economic unit, not 78 five-minute independent trials; 42 UTC crypto days are not 1,008 independent returns.

## 6. Functional implementation and acceptance

Source: runtime30/fwn9_p9m_c23_market_data_audit.cjs. It validates timezone-qualified timestamps, half-open numeric UTC cutoff, New York DST, exchange sessions/early closes, duplicate and missing bars, feed-specific regular coverage and descriptive volume/volatility. It also computes the opposite net-fill counterexample and explicit six-variant receipt readiness. No customer-supplied self-attestation field can flip the financial GO gate.

Tests: tools/fwn9_p9m_c23_market_data_audit_test.cjs — 18 fixed engineering tests including false end-boundary inclusion, missing/duplicated RTH bars, summer DST, half-day, tampered prices, fake receipts and real-fill nonidentification. Existing source M9/C22/C21/C20/C16 regression workflow remains required.

Evidence file: evidence/modulation11/fwn9_phase9m_c23_market_coverage.json. No raw market bytes or private customer account data are published in the repo; the connected tool query does not itself create a cryptographically authenticated execution receipt. The source code requires original market input for a third party to reproduce aggregates.

For future confirmation, pre-register the exact six policies before an untouched sample; use the original 72-hour purge/embargo; validate source receipt IDs, order fill/partial/cancel/reject events, quote-at-decision and receipt clocks, fee and cash ledgers, unmatched candidate opportunity logs, and market-price attainability. Compare net geometric growth in one reconciled funded book vs CASH; any original-policy control not actually executed must be disclosed as a modeled, uncertainty-bounded counterfactual. Correct FWER and dependence at the day/group level, not raw five-minute intervals.

**Final: no real net optimal window found. N9-S NO_GO; 3,200 final M10 accounts sealed; 0 new signals, market seeds, economic accounts, orders, deployments, merges, or recursive optimization restarts.**
