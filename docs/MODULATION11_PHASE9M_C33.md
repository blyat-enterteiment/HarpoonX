# HarpoonX M11 C33 — CASH control completeness + Alpaca GET receipt provenance

**Status:** draft, zero new economic accounts, signals, fills, orders,
deployments, merges, final M10 openings or recursive optimization.
**N9-S NO_GO**.

## Problem reproduced in C25

The C25 importer and native read-only exporter both rejected an empty
instrument list even when the observed portfolio had zero positions and
the entire window had zero orders or fills. A genuine preassigned CASH
arm in C29 cannot be reconciled if this restriction remains.

C33 permits an empty catalog **only** when BOTH account checkpoints
are position-free, the complete order list is empty, and every activity
page is free of FILLs. All other C25 cash, NAV, external costs,
pagination and identity checks remain unchanged. A hidden order,
position, or fill still fails closed. A CASH block may have nontrading
cash activities but it must account for them and its complete costs.

## HTTP GET witnessed BEFORE decoding

C33's new `fwn9_c33_broker_get_witness.cjs` wraps the exact transport
called by the ORIGINAL C25 read-only Alpaca exporter. It requires the
PAPER HTTPS origin, the original endpoint allowlist and GET with
redirects blocked. It records the SHA-256 of raw response bytes, HTTP
status, hashed request query and local send/receive timestamps before
the original C25 parser can proceed.

The local journal `fwn9_c33_broker_get_journal.cjs` keeps a private
0700 directory and 0600 manifest/NDJSON file with chained SHA-256,
fsync and single-writer lock. It does **not** save account IDs,
HTTP bodies, API keys or query cursor values. A failed write prevents
the C25 parser from consuming the response. Stale locks require manual
investigation; local clock times and body hashes are not broker-signed
receipts or independent time stamps.

## Locally invoked PAPER capture (not run by CI)

On an authorized machine where user-owned Alpaca PAPER Trading API
credentials are present in the local environment (never in GitHub or
the chat), the new optional CLI performs the existing C25 baseline
and finish using the witnessed transport:

    node tools/fwn9_c33_paper_capture.cjs --stage baseline --mode PAPER --out /private/c25-begin.json --get-journal /private/c33-begin

    node tools/fwn9_c33_paper_capture.cjs --stage finish --mode PAPER --baseline /private/c25-begin.json --out /private/c25-finish.json --cost /private/costs.json --get-journal /private/c33-finish

    node tools/fwn9_c25_readonly_cli.cjs --bundle /private/c25-finish.json

Each output path must be new, stored privately outside the repo and
must not reside under M10 holdout/final paths. The two C33 journals
are intentionally independent and have separate receipt heads.

The exporter remains read-only. No paper or live order submission
occurs and this PR cannot authorize such calls. The existing C25
bundle exposes full private account data and must NOT be committed,
uploaded, or shared outside an approved secure environment.

## What the evidence proves, and does not

C33 validates software integrity of HTTP response capture, C25 ledger
consistency and the possibility of a real no-trade CASH block. It
does **not** independently authenticate Alpaca as the upstream broker,
prove that all orders were emitted by a deployed HarpoonX instance,
guarantee complete pagination beyond the declared API responses,
capture knownAt of earlier fills absent a contemporaneous listener,
or prove an exchange queue position. Historical GET data cannot
retroactively recreate predecision receipt times.

In the connected ChatGPT environment only the Alpaca market-data
connector is available, not the user's private Trading API receipts.
Render service enumeration has not identified the running service.
No private broker calls are made by this CI. C26, the C27/C28-C32
event link, option contracts, external preregistration and prospective
one-book randomized comparison remain material blockers.

## Reproduce offline engineering tests

    node --test tools/fwn9_c33_broker_receipt_test.cjs
    node --test tools/fwn9_c25_alpaca_readonly_exporter_test.cjs tools/fwn9_c25_broker_export_ingest_test.cjs

Synthetic fixtures are ONLY for engineering regression, with no
claims of observed account profitability. Never promote NO_GO.
