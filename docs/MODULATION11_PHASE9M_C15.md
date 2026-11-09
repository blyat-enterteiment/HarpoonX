# HarpoonX — M11 Phase 9M-C15: financed WEAK wealth exclusion

**Admission decision: N9-S NO_GO (as of 2026-11-08).** This is an analytic exclusion-screen implementation, not a claim that the native replay is mathematically incapable of succeeding or that any real alpha is proven. PR #7, original engines and all 3,200 sealed M10 final accounts remain untouched.

## Exact conditional inequality

Let W0=20,000 USD, D=176 calendar days and gamma=expm1(0.000025*1.1/8). For each of 126*78*8=78,624 frozen WEAK intraday substeps k, q[k,a]>=0 is the funded quantity of a held **before** the Gaussian innovation and S[k,a] its reference price. Let A=E_WEAK sum[k,a] q[k,a]*S[k,a], U=E_WEAK sum[k] positive execution credits against a time-aligned actually tradeable reference, and C* a proved minimum total cost. All fill decisions must honor knownAt and all capital transfers, partial fills, rejections and receipts must reconcile.

By Gaussian conditional compensation, the weak drift per asset is never above gamma. WEAK overnight Gaussian moves and symmetric 0.97/1.03 jumps have conditional multiplicative mean one. Therefore E W_T <= W0+gamma*A+U-C*. When W_T>0, Jensen implies:

    E_WEAK [log(W_T/W0)] / 176 <= log(1+(gamma*A+U-C*)/W0) / 176

This is conditional on **actual** self-financing, predictable long inventory, consistent mark/reference execution support, full-book capital and positive terminal wealth. The 12% limit is an admission/reservation cap, NOT a continuous exposure ceiling; no such cap is used.

## Economic barrier

At 1 bp mean daily log hurdle, the allowed threshold increment equals:

    W0*expm1(D*0.0001) = 355.1158528283328 USD

WEAK is excluded from hitting the hurdle if a rigorously proved population upper for A and U obeys:

    gamma*A_upper+U_upper-C_lower < 355.1158528283328 USD.

With only contract calendar fees, this becomes gamma*A_upper+U_upper < 531.1158528283328 USD nominal, or < 707.1158528283328 USD stress. If U_upper=0 as an **illustrative algebraic assumption only**, thresholds are 154,506,164.36 USD·steps nominal and 205,706,076.36 USD·steps stress. Relative to 78,624 steps times initial capital, these equal average dollar-notional reference shares 9.825636% and 13.081634%; they are NOT empirically observed exposures or a new portfolio limit.

## Certificate status

Population-level A and U have not been independently certified; in particular OHLC high compatibility does not establish executable eight-substep fills. Source hashes, original costs and full cash/receipt-clock invariants are mandatory. Coverage of partial entries, rejection, outages, market impact and the multicell coordinator remains unverified. The conditional inequality is a potentially useful NO_GO sufficient test, never a GO proof. An upper bound above the hurdle is inconclusive.

## Files

- research/modulation11/fwn9_phase9m_c15_protocol.json — derivation scope, refutation and original contract.
- tools/fwn9_p9m_c15_economic_gate.py — standard-library gate that reports missing A/U as UNIDENTIFIED, never zero; includes frozen M9 Git blob verification.
- tools/test_fwn9_p9m_c15_economic_gate.py — 11 unit tests; they check mathematics, boundary, adverse inputs, frozen-source tampering and no-promotion.
- .github/workflows/fwn9_p9m_c15.yml — scoped syntax, lint, strict types, unit tests, provenance and benchmark.

Work on a separate unmerged research branch. No new economic accounts, synthetic market seeds, candidate policies, live orders, broker activity, deployment or automation reactivation.
