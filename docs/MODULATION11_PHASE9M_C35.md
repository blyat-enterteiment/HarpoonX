# HARPOONX M11 C35 — Alpaca PAPER native trade_updates knownAt capture

**Scope:** read-only, opt-in PAPER WebSocket receipt capture; not an order
gateway. Frozen C29 statistics, six C22 variants, 72-hour holding, 20,000 USD
financed-book capital, 0.25% admission risk, 12% gross admission and
M10 holdout remain unchanged.

## Why native streaming changes evidence quality

Alpaca's official Trading API describes an authenticated
`wss://paper-api.alpaca.markets/stream` channel, with `auth` followed by
`listen: trade_updates`. It emits fills/partial fills, cancellations,
rejections and broker order timestamps. PAPER delivers binary WebSocket
frames (the documented payload is JSON); the source example includes
`execution_id`, `order.id`, `timestamp`, `price` and `qty`.

Primary source:
https://docs.alpaca.markets/us/docs/websocket-streaming

C35 now records the actual local receipt time **at the moment the
WebSocket event is received**, not guessed retroactively from a
historical C25 GET response. It preserves the upstream broker timestamp,
source order/execution IDs and exact decimal price/quantity in a PRIVATE
journal. The collector does not create a buy/sell order and its outgoing
messages are restricted to authentication and subscription.

## Implemented

- `runtime30/fwn9_c35_paper_trade_updates.cjs`: strict native event parser,
  auth/listen acknowledgement state machine, nanosecond comparison, duplicate
  execution-ID guard, explicit unsupported multi-leg options state and
  C25 **exact fill matching** by broker order, symbol, side, timestamp,
  quantity and price. No unverified join by `execution_id=activity.id`.
- `runtime30/fwn9_c35_paper_stream_journal.cjs`: private 0700 directory,
  0600 manifest and journal, exclusive writer, SHA-256 chained events,
  synchronous fsync, full restart verification, explicit auth and listen
  preconditions, no silent recovery after disconnect.
- `tools/fwn9_c35_capture_paper_stream.cjs`: user-invoked, FINITE (1–3600
  seconds) stream capture. Connects only to PAPER and sends only `auth` and
  `listen`. No retries. Unexpected disconnect leaves the writer lock for
  human incident review. No secrets in logs. Running in CI against a broker
  is expressly prohibited.
- `tools/fwn9_c35_paper_stream_test.cjs`: synthetic engineering fixtures,
  native C25 cash reconciliation and negative tests for source clock,
  authentication, missing/duplicate events, options, I/O integrity.

This provides an honest *locally observed* knownAt for streamed order
updates **when the collector is connected and authenticated**.
No third-party timestamp or provider-signed event message is supplied.
The stream can disconnect and cannot retroactively reconstruct missed
events. Ordinary historical C25 GET reconciliation remains mandatory.
The collector is never a trade execution authority.

## Manual local usage (NOT executed in this PR)

Use private PAPER credentials from the local secret manager; never copy
secrets or raw event journals into GitHub or the chat.

    node tools/fwn9_c35_capture_paper_stream.cjs --mode PAPER --out /private/C35-new-capture --seconds 600

The program prints only a compact, non-sensitive summary when successful.
The private file contains broker order IDs and prices; access must remain
restricted. A successful ten-minute capture is an **observation interval**,
not proof that market opportunities or future broker events were complete.

## Critical link to C25, C26, C29 and C34

- C25 still reconciles complete original account snapshots, activities,
  orders, cash, fees and positions. C33 GET witness remains an independent
  read-only source log.
- C35 matches streamed fills to C25 activities only when order ID,
  instrument, side, nanosecond execution time, exact quantity and price
  uniquely agree. It rejects an ambiguous match. These checks cannot
  prove origin identity beyond the authenticated transport.
- C26 must still establish quote known before decision and decision before
  submission; a C35 fill timestamp does not supply this previous quote.
- C34 RFC3161 signature is required on the frozen, pre-outcome study.
  A local test CA cannot satisfy independent registration.
- C29 remains one continuously financed account with six arms plus CASH
  and ORIGINAL in randomized blocks. Unexecuted arms receive no fills.

Option execution and settlement require additional C25-C26 adaptation,
including multiplier, legs, exercise, clearing and commissions.
No option fill may be promoted by this new source.

## Reproduction and acceptance

    node --test tools/fwn9_c35_paper_stream_test.cjs

The CI workflow also runs C30–C34 regressions. These tests are
synthetic software validation ONLY. No user-private Trading API event
has been observed in this PR; no READ-ONLY Render deployment exists in
the accessible workspace. No PAPER/LIVE orders, merge, new market
seeds or economic trials. The 3,200 M10 accounts remain sealed.

**N9-S NO_GO.**
