# HarpoonX — M11 Phase 9M-C16: native accounting to A and U, independently reconciled

**Result: PASS for a read-only native replay receipt bridge over the pre-existing C14 deterministic engineering fixture.** This is not WEAK population certification, not complete 72-hour live execution, and not N9-S promotion. All market research final M10 accounts (3,200) remain sealed.

## Integration

`runtime30/fwn9_p9m_c16_native_au_bridge.cjs::audit({native,data,sessions,calendarCostUsdPerDay})` consumes the **actual** `replayFundedPortfolio` result, source price bars, and the same sessions used by the native replay. It does not call the market generator, strategy search, broker, policy selection or seed source. Validation forces original native source shape (`HISTORICAL_MODELED_OHLCV;NOT_BROKER_RECEIPTS`), cash shares with no corporate actions, 78 bars/session, original commission/charge parity, two assets, explicit fill chronology and full terminal cash/equity reconciliation.

Native `inventoryEvents` carry `at` (physical execution) and `knownAt` (knowledge time). Entry proceeds cannot use exit receipts that are not known at entry. `modeledNoFills` do not create positions. Position and cash are reconciled directly, not inferred from the strategy's PnL scalar.

### Exact measurement semantics

Let B be the set of existing five-minute bars for the replay evaluation sessions. Original M9 bars are generated from eight Gaussian substeps, but the native data retains only OHLC, not the ordered tape. Therefore `A` and `U` cannot be measured exactly without additional source-provenance records.

For each bar and asset, the observer reconstructs the long quantity just after opening buys, q_before_exit, and the long quantity surviving every modeled bar-end exit, q_after_exit. The conservative A *pathwise envelope* is

    A_low = SUM_{bar,asset} 8 * q_after_exit * bar_low
    A_high = SUM_{bar,asset} 8 * q_before_exit * bar_high.

The asymmetric quantities are intentional: an OHLC stop or target could execute before the eighth substep even when the modeled receipt records `at=bar.end`. Counting all eight exposures as guaranteed after an early exit would be incorrect. Positions carried between bars and across overnight windows are NOT artificially reset.

Under the conditional assumption that a fill's tradeable reference lies within its original source bar's eight-substep price range, the positive execution-credit *pathwise upper* is

    U_high = SUM_open q * max(bar_open - fill_buy, 0)
             + SUM_close q * max(fill_sell - bar_low, 0).

`U_high` is not the actual favorable execution credit, not a broker fill measurement and not a proof that an OHLC stop/target was achievable in discrete time. Trades outside guarded source support fail closed. Transaction fees and calendar charges are independently reconciled.

## Independently verified engineering observations

The source is the **same fixed C14 fixture** (two previously defined engineering signals SYNA:60 and SYNB:90, six evaluation sessions, no stochastic seed generated). It produces 468 existing source bars, 3,744 potential intraday substeps and four modeled physical fill events.

| Metric | Decimal-46 independently reconstructed |
|---|---:|
| A_low, USD·substeps | **1,397,670.4** |
| A_high, USD·substeps | **1,417,539.2** |
| U_high, USD | **0.51** |
| Terminal financed cash, USD | **19,990.500** |
| Terminal cash/native curve match | **PASS** |
| C15 expected population A, U | **UNIDENTIFIED** |

The values above apply ONLY to this engineering fixture. They are neither expectation bounds over WEAK nor estimates for 126 evaluation sessions. Feeding this A_high or U_high directly into the C15 176-day inequality would be invalid.

## Independent verification and economic handoff

`tools/fwn9_p9m_c16_decimal_accountant.py` receives source bars and events; with Decimal precision 46, it independently reconstructs inventory, prices, cash, fees, complete calendar costs and the A/U envelope. It does not use JS-calculated totals as calculation inputs. Tampered `A_high`, `U_high` and terminal cash values are independently rejected.

`tools/fwn9_p9m_c16_c15_handoff.py` reads those measurements only after this independent check and frozen protocol validation. It returns the original C15 nominal and stress hurdles with expected A and U **null**, since a deterministic path is not a population certificate. Recursive candidate search and N9-S promotion stay blocked.

Validation of the corrected bar-exit uncertainty: [GitHub Actions run 42560563816](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42560563816) — 11/11 native tests, Python Ruff and mypy strict, Decimal46 independent audit, three tamper controls, source hashes PASS. The earlier inconsistent interim bridge lower was explicitly corrected; the intermediate CI failure is retained for traceability. Performance measurement: 200 read-only fixture audits in 314.722 ms on that CI runner; this is neither trading latency nor population research throughput.

## Local reproducible checks (from repo root)

```bash
node --test tools/fwn9_p9m_c16_native_au_test.cjs
node tools/fwn9_p9m_c16_native_au_test.cjs --emit-c16 > /tmp/c16_native.log
python -B tools/fwn9_p9m_c16_decimal_accountant.py /tmp/c16_native.log
python -B tools/fwn9_p9m_c16_c15_handoff.py /tmp/c16_native.log research/modulation9/protocol.json
```

These scripts do not connect to any broker or mutate positions. They reconstruct the **existing deterministic C14 engineering fixture**, not a new candidate or market replay sample. The fixed engineering fixture is not a new research economic account.

## Admission and next proof requirements

**N9-S = NO_GO**. The C16 measurement bridge is ready for existing, provenance-verified native outputs, subject to its strict event-grid contract. To certify a population bound, we still need the original ordered eight-substep tape (or a mathematically valid alternative), comprehensive self-financing/receipt-clock invariants for the entire native policy class, justified expectation upper bounds across frozen WEAK with no final holdout leakage, and operational fault coverage for partial entries, rejects, outages, price impact and multicell orchestration. None of those are silently inferred from C16 fixture success.

No new strategies, no stochastic market seeds, no economic research accounts, no opening of final M10, no live orders, no broker, no deployment, no merge and no automation reactivation.
