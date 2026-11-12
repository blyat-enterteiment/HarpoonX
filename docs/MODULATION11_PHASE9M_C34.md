# HARPOONX M11 C34 — RFC3161: registro prospectivo externamente comprobable (NO_GO)

**Scope:** source, signed evidence tooling and falsifiable gates. C34 does
not run the algorithm, schedule capital, make a timestamp request over the
network, access M10 or send PAPER/LIVE orders.

## Why GitHub or a local hash was insufficient

A C29 plan file, SHA-256 and local file-modification time can all be
reconstructed after results. Even an Ed25519 signature from an
unidentified party cannot independently establish creation time.
The existing C28 signed head covers integrity only conditionally.

C34 builds ONE write-once exact-byte envelope binding:
- C29's 8-arm, 72h trading, 72h embargo, one-hour review plan,
  capital 20,000 USD and risk constraints;
- the six forward-only composite policy definitions of C32 (which must
  have been defined BEFORE the plan); they **do not** retroactively
  establish the six historical C22 policies' semantics;
- hashes of all critical native code: producer, C25-C26 broker adapter,
  C28 comparator, C29 randomization and C34 verifier.

## RFC3161 cryptography and limits

C34 verifies **both** the timestamp response against the exact
envelope file (`openssl ts -verify -data ...`) **and** the matching
original timestamp request (`-queryfile`), which checks the nonce.
The signing chain is checked with the pinned CA PEM. It extracts the
signed `genTime` and requires the TSA time to fall between C29's
registeredAt and 72h before the first scheduled block. It refuses
tampered plan bytes, mismatched source code, changed policy versions,
different RFC3161 nonce, signature mutation, wrong CA pin or a late
signed timestamp.

The certificate pin is provided by the user. **A CA can be self-issued
by the same researcher and still pass cryptographic verification.**
Accordingly, a successful run reports:
`requestNonceAndEnvelopeMessageImprintCryptographicallyVerified=true`
but `tsaSignerAndTrustRootIndependentlyVetted=false`,
`independentlyAuditedPreregistration=false` and `N9S=NO_GO`.
The user must independently establish custody, identity, time service
and publication of the CA fingerprint *before* the study. Tests use
only an ephemeral self-issued TEST CA. Never use that authority to
claim public/financial preregistration.

Official RFC3161/OpenSSL reference:
https://docs.openssl.org/master/man1/openssl-ts/

## Procedure (private / no broker / no network actions by these scripts)

Prerequisites: a newly frozen private C29 plan, a C32 forward-only
binding generated before that plan and the identical source-code
version. Original C29 rules are unchanged. User intervention and
external notarization are required for real evidence.

First, construct the exact envelope once (0600):

    node tools/fwn9_c34_prereg_cli.cjs --prepare --plan /private/plan.json --binding /private/binding.json --out /private/c34-envelope.json

Next, generate an RFC3161 timestamp request locally:

    openssl ts -query -data /private/c34-envelope.json -sha256 -cert -out /private/c34-request.tsq

Deliver the request to an independently selected and vetted TSA using
the TSA provider's documented process. **This code does not send it**.
Keep the original signed DER response, original query and vetted
CA chain under controlled storage. Have the CA fingerprint established
outside this source tree before any outcome is observed.

To verify the delivered token against the exact envelope and original
request:

    node tools/fwn9_c34_prereg_cli.cjs --verify --plan /private/plan.json --binding /private/binding.json --envelope /private/c34-envelope.json --query /private/c34-request.tsq --response /private/c34-response.tsr --ca /private/trusted-tsa-ca.pem --ca-sha256 PINNED_SHA256

If a separate signer/intermediate cert is required, supply
`--signer /private/tsa-chain.pem`. Never post API keys, CA private
keys or account exports to GitHub.

## Delayed activity restatement guard (C34-L)

The Alpaca Trading API activity interval is based on record creation time,
not necessarily when a trade economically settled. A fee or correction can
be created after a C25 block's terminal snapshot. The new
`fwn9_c34_delayed_activity_census.cjs` validates a broader PAPER
activity requery. It requires every old ID and exact record digest to
reappear, flags newly created fees and other activities, and rejects
missing old events, changed fees, duplicates, unknown `created_at`,
account substitution and an unextended query window.

A requery containing zero additional activities cannot prove that the
broker will never report a later charge. C34 therefore leaves
`financialGO=false` even when the supplied activity history passes.
This is an offline consistency gate, not a live broker connection.

## What still prevents N9-S

- No actual independently vetted timestamp service was called;
  cryptographic fixtures cannot prove registrar independence.
- C33 transport currently provides only locally observed response
  hashes for authorized Alpaca PAPER GET; no user's private broker
  account activity has been observed here.
- The producer is not connected to Render or prospectively joined to
  C27/C28, and option execution, fees, exercise and settlement are not
  certified.
- Alpaca activities are retrieved by creation date, while some
  nontrade costs may appear after trading. Every block needs
  late-activity restatement checks before being called final.
- No eight-arm one-book randomized financial trial has started.
  A mathematically small p-value is not automatically a bound on
  population net growth or approval for trading.

## Reproduce engineering tests

    node --test tools/fwn9_c34_rfc3161_prereg_test.cjs

The tests issue genuine RFC3161 signatures with local, explicitly
non-independent keys. They test crypto plumbing only. N9-S NO_GO.
