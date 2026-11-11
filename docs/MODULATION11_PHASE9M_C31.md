# HarpoonX M11 C31 — witness of native post-filter invocation (NO_GO)

The study remains under a frozen C29 economic protocol; C31 is a strictly
read-only source-lineage diagnostic. No generator, broker, order, strategy,
profit8_replay, historical results, or final M10 seed has been changed.

## Native source observed without creating new work

Original runtime30/plugins.js exports Plugins.evaluate(book,market,enabled,now).
The engine's coordinator calls this method from entries(). The native
catalog uses IDs such as options-call-breakout; the six H22 policy IDs in
C28 are different research-window identifiers and are not bound one-to-one
to executable original plugin methods.

C31 attaches an optional wrapper to an existing native Plugins instance.
It does NOT call evaluate on attachment and does not schedule work.
Only when the original engine would already invoke evaluate does the wrapper
record the method version, the selected native plugin IDs, the invocation
and return clocks, and the already-returned emitted signal IDs. It returns
the original result object unchanged. It does not record market data, account
secrets, quotes or broker credentials. On evidence-sink failure, the result
is blocked rather than passed downstream. On native error, an error
classification is persisted and the original exception is rethrown.

Crucially these are POSTFILTER observations: they do not prove that all
original internal eligibility tests ran, nor the C28 per-policy prefilter
source obligations. No native C22 mapping is fabricated.

## Durable local witness

runtime30/fwn9_c31_native_call_journal.cjs writes each witness to a private
mode-0600 file with exclusive creation, fsync and a chained SHA-256 content
digest under a 0700 directory. It verifies the complete prefix after restart,
rejecting missing or changed records, foreign files and changed permissions.
Its local integrity hash is not an independent trusted timestamp or exchange
authentication.

## Reproduction and CI

    node --check runtime30/fwn9_c31_native_postfilter_witness.cjs
    node --check runtime30/fwn9_c31_native_call_journal.cjs
    node --test tools/fwn9_c31_native_lineage_witness_test.cjs

The tests exercise original Plugins.prototype.evaluate on a no-market,
zero-enabled-plugin instance; no financial signals or orders are generated.

## Gates remaining

1. Record actual PRE-FILTER native decisions at the original source, not just
   wrapped returns, including all zero-result calls; tie C28 policy windows
   to explicitly identified original plugin logic and prove semantic parity
   before prospectively treating those as C22 variants.
2. Reconcile authenticated private Alpaca PAPER account activity and fees,
   distinguishing C25 source transport from a truly independent broker
   source attestation. Options require an execution and settlement contract.
3. Independently pre-register C29 or a changed C29 successor before observing
   outcomes, with externally verifiable receipt time and signed hash.
4. Only then perform the frozen one-account block-randomized prospective
   comparison. Never assign modeled fills to nonexecuted C22 variants.

N9-S NO_GO; M10 3,200 accounts sealed; zero new economic accounts, market
seeds, trading signals, broker orders, deployments, merges or optimizer loops.
