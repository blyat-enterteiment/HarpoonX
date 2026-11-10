# HARPOONX — FWN9 / M11 C26: causal quoted execution, source-time and fill reachability

**Verdict: Scoped software-engineering and accounting controls PASS; economically attainable fills and N9-S remain NO_GO.** This branch has no live/paper orders, new signals, market seeds or economic trading trial accounts. All 3,200 M10 final accounts remain sealed. Original M9 simulation and stop-first OHLC engine are untouched.

## 1. C25 is re-used, not replaced

C26's `runtime30/fwn9_c26_causal_quote_fill_bridge.cjs` first invokes the existing read-only `runtime30/fwn9_c25_broker_export_ingest.cjs` certificate, which itself invokes source-native `NetAccountLedger.snapshot()` and `.activity()` and independently reconciles fixed-decimal USD-8 cash, shares and FEE. If C25 reports a mismatch, C26 throws before any market-execution claim.

The original private C25 account export and an additional predecision observation journal are combined into a single **OFFLINE** JSON payload with `schema=HARPOON_FWN9_C26_CAUSAL_QUOTE_FILL_BUNDLE_1` and `capture_mode=OFFLINE_PERSISTED_OBSERVATIONS`.

## 2. Required records

- `account_export`: the fully paginated, single-account C25 export with orders, fills, NAV/cash/positions and declared external-cost coverage.
- `choices.quotes`: `id`, `symbol`, `feed` (SIP/IEX for US stock, US crypto feed for spot), `market_at`, **actual locally observed** `known_at`, `bp`, `ap`, `bs`, `as`. Prices and sizes are nonnegative decimal strings with at most 8 digits after the point; crossed quotes and wrong asset feeds reject.
- `choices.decisions`: each `order_id`, its `quote_id`, `side`, `decision_at`, `known_at`, and `source=LOCAL_OBSERVATION_JOURNAL_CLAIM`; a field claiming journal origin is **not independent proof** that this journal exists.
- `choices.receipts`: exactly one per actual `FILL` activity, with original `activity_id`, `order_id`, `symbol`, `execution_at`, **local** `known_at`, and `kind=BROKER_ORDER_UPDATE_LOCAL_JOURNAL_CLAIM`; receipt information must not be used to finance orders before it became available.

**C26 requires nanosecond-stable causal inequalities**, not only Date.parse millisecond truncation:

    quote.market_at <= quote.known_at <= decision.decision_at
    decision.decision_at <= decision.known_at <= order.submitted_at
    order.submitted_at <= fill.execution_at <= fill_receipt.known_at

A quote must have been locally received within five seconds of submitting the order, which is an explicit **frozen engineering freshness threshold**, not evidence that the quote guaranteed execution or that five seconds is economically optimal. Quote and receipt sources are hashes of caller-supplied JSON; neither a hash nor a source-name string authenticates a broker or exchange.

### Nanosecond look-ahead failure

Events at `2026-11-06T14:29:58.000000000Z` and `2026-11-06T14:29:58.000000100Z` have identical JavaScript millisecond values but different causal order. C26 uses integer nanosecond comparisons and **rejects** a quote received 100ns after its claimed decision. It likewise rejects a fill receipt mismatched by one nanosecond. The original C25 API snapshots remain limited by their local millisecond receipt clock; C26 doesn't represent them as exchange-synchronized.

## 3. Implemented cost measurement (not profit)

For observed long buy FILL with quantity q and executed price P against a predecision known BBO:

    shortfall_buy = q * (P_fill - ask_predecision)

For sell FILL:

    shortfall_sell = q * (bid_predecision - P_fill)

Positive means a worse execution than the earlier quote; negative means price improvement. This is a **reference-price execution diagnostic**, not a complete implementation shortfall or a live policy edge. The source quote predates the fill and price may move in between; spread, commission, true order arrival and impact are not identified by a predecision quote alone. Fees already included in broker NAV must never be charged twice in portfolio returns.

Per fill the output also records source spread, local knownAt chain, reported L1 displayed quantity and whether the reference quote is merely **declared** as SIP or IEX. Top-of-book size is not depth, queue position or a fill guarantee; SIP feed does not provide an order's executed allocation; IEX is not consolidated NBBO.

The exact C26 example values used in CI (buy two synthetic shares at $100, sell one at $110, synthetic fees $1, original NAV reconciled) are **engineering fixtures only**. The test measures an illustrative *negative* shortfall $-0.06 against artificially supplied earlier quotes. It is not a result from HarpoonX or a user account.

## 4. Functional use

The source-time extension is deliberately separate from C25's Trading API GET-only collector, because historical downloads cannot produce a truthful predecision `known_at` field. It must be sourced from the existing prospective `runtime30/quant_observations.js` journal or another audited live local capture mechanism, with independent origin/receipt verification still pending.

To inspect an already prepared private C25+quote/decision/receipt JSON file:

    node tools/fwn9_c26_readonly_cli.cjs --bundle /carpeta-privada/c26-evidencia.json

Optionally save the complete per-fill diagnostic to a local file created exclusively with mode 0600:

    node tools/fwn9_c26_readonly_cli.cjs --bundle /carpeta-privada/c26-evidencia.json --out /carpeta-privada/c26-dictamen.json

If no bundle is supplied, C26 returns `BLOCKED_CAUSAL_BID_ASK_AND_BROKER_ORDER_RECEIPTS_NOT_AVAILABLE`. It never fetches private data itself, prints account identifiers, executes a strategy or places orders. There is no silent fallback to synthetic fill prices or model market volume.

## 5. Scope of tests and what they do NOT establish

Source code: `runtime30/fwn9_c26_causal_quote_fill_bridge.cjs`. CLI: `tools/fwn9_c26_readonly_cli.cjs`. Tests: `tools/fwn9_c26_causal_quote_fill_bridge_test.cjs`.

C26 includes 27 deterministic adversarial controls: original partial fill/order identity; quote known before decision; stale/future quote; same-millisecond but different nanosecond ordering; duplicate receipt/quote; wrong side/feed; IEX-versus-SIP distinction; insufficient displayed size not confused with impossibility or certainty; missing receipt/decision fail-closed; CSV/JSON input invalid; local CLI 0600 exclusive report and no M10 holdout path.

CI also runs 176 existing C16–C25 tests including C16 independent Decimal-46 accounting and original C15 null expectation inputs. Total: **203 test cases**. These are source-contract tests; CI uses no account credentials, no broker GET, no market seeds, no new economic trial accounts. No source-level existing economic code is changed.

The original C21 theorem still refutes universal equality of native OHLC stop-first fills and eight ordered-substep first-cross execution. Even a C26 perfect causal attachment would not establish actual queue/depth consumption, fill attainability of all counterfactual C22 variants, or a familywise-adjusted return out of sample.

## 6. Next acceptance barrier

To progress toward FWN9's economic GO, an independent source must supply genuine private C25 order/activity/cash evidence together with contemporaneous quote snapshots and received-at timestamps for all admissions/rejections. C27 must instrument all native pre-bar stop and target state, and its complete candidate opportunity set, before any new OOS evaluation is registered; compare net log growth vs CASH/original with one funded portfolio and proper risk and cost budgets.

**Financial verdict: N9-S NO_GO.** Source interface and deterministic validation are implemented and independently tested in GitHub CI, but actual broker-origin fills, non-executed opportunities, full account provenance, net alpha and optimal time-of-day have not been certified.
