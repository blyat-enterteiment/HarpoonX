# HARPOONX — M11/9M-C18: funded-WEAK wealth supermartingale dual

**Verdict: C18 focal mathematical derivation and independent Decimal50 passed; N9-S NO_GO unchanged.** No RNG, no new price path, no signal, candidate, economic account, final M10, broker, order, deploy, merge or automation restart.

## 1. Evidence already established (C17)

PR #9 preserves the original M9 generator's ordered eight-step tape for *registered development seed 730101*. 157,248 intrabar price observations for SYNA/SYNB and 126 evaluation sessions were source/mark checked; the cross-run audit-only 7-decimal digest is `a173af77533f7bbe2b0a3ae54485ee64bc4f33cc83a01b860efdb0702d102398`. Raw IEEE hashes differ by about 3.41e-13 USD/share across independent GitHub runners and are **not bitwise identical**. The historical full-input archive hash has not been proven equal to the regenerated market-only hash. C17 did not open the final M10 holdout.

C17 gives finite WEAK expectation upper envelopes for a restricted long bar-open-only financed class, but `E[A] <= 1.32e33 USD·substeps` and `E[U] <= 1.9806e30 USD` are economically vacuous. C18 does not overwrite the source law, change M9/10 protocol, or treat these as measured native account expectations.

## 2. New conditional theorem: the original funded-wealth recursion

Let `F_k` be the information before original WEAK substep `k`, `k=0,...,N-1`, `N=126*78*8=78624`. Denote physical cash by `C_k>=0`, long predictable shares by `q_{a,k}>=0`, tradable source price by `S_{a,k}>0`, and wealth `W_k=C_k+Σ_a q_{a,k} S_{a,k}`. An actual step-aligned fill must use the same predictable filtration, with any favorable execution price improvement recorded as signed `Y_k` rather than treated as future price movement. Its positive part `(Y_k)_+` has finite total expectation `U=Σ E (Y_k)_+`. All broker/transaction/calendar charges have nonnegative expected total and are bounded below by a proved cash charge `C_min`. No external capital additions or positive overnight fill/financing credits.

The original compensated WEAK generator has `E[S_{a,k+1}/S_{a,k} | F_k]=exp(drift_{a,k}/8)` with predictable drift at most `δ = 0.000025 * 1.1 / 8`. This inequality holds regardless of the Gaussian correlation, regime, mixture variance or volatility scale, provided the current shock is not leaked into `q_{a,k}`. Overnight Gaussian+symmetrically compensated jump transitions have conditional arithmetic mean one.

Thus `rho=expm1(δ)` and `G=exp(Nδ)` yield

    E W_(k+1) <= (1+rho) E W_k + E[(Y_(k+1))_+].

Because `q*S <= W_k` under physical nonnegative cash, placing every beneficial credit at the beginning is a conservative algebraic upper operation. For `H = (G-1)/rho`,

    E[A] <= (W0 + U) H,
    E[W_T] <= G*(W0 + U) - C_min.

Assuming positive terminal wealth (or log expectation equals -infinity on bankruptcy), Jensen gives

    E[log(W_T/W0)]/176 <= log((G*(W0+U)-C_min)/W0)/176.

**These are bounds for the stated abstract source-step-funded class. The full OHLC native replay has not yet been shown to meet all its execution-time and receipt assumptions.** Original `grossFraction=0.12` is an *admission* limit, not a continuous notional restriction.

## 3. Independent numeric results

Freeze: W0 = 20,000 USD; N = 78,624; calendar days = 176; nominal minimum 176 USD, stress 352 USD; unchanged daily log hurdle 0.0001.

| Output | Value |
|---|---:|
| `rho` conditional max arithmetic substep drift | 3.4375059082098956e-6 |
| `G` maximum fully-invested expected gross bound | 1.3103181888874473 |
| `H` geometric factor | 90,274.22706279727 (approx.) |
| `E[A]` bound with **hypothetical U=0** | 1,805,484,541.2559454 USD-substeps |
| `E[W_T]` upper, nominal U=0 | 26,030.36 USD (approx.) |
| `E[W_T]` upper, stress U=0 | 25,854.36 USD (approx.) |
| Expected daily log upper, nominal U=0 | **14.97337617507584 bp/day** |
| Expected daily log upper, stress U=0 | **14.587904810893214 bp/day** |
| Economic hurdle | **1.000 bp/day** |

The hypothetical `U=0` class yields A about **24 orders of magnitude** below C17's very loose 1.32e33 envelope, but its gross-drift upper is still far above the original N9-S hurdle. **No GO or mathematical impossibility follows.**

For a *new, independently demonstrated* uniform conditional continuous exposure fraction `f` with `(Σ qS)<=f W` at every innovation, and still U=0, a tighter sufficient-exclusion test would be

    [1+f*rho]^N * W0 - C_min < W0*exp(176*0.0001).

Solving for the maximum admissible `f` in *that proposed proof* gives **9.697438719188187% nominal**, and approximately **12.8557% stress**. This is a sensitivity/break-even proof requirement, **not evidence that native portfolios maintain those fractions**; it is invalid to substitute the original 12% admission ceiling as a continuously maintained `f`.

## 4. Engineering and quality gates

- `research/modulation11/fwn9_phase9m_c18_protocol.json`: preregistered derivation, failure modes and zero budget.
- `tools/fwn9_p9m_c18_funded_wealth_dual.py`: model/source SHA checks and analytical C18 dual; `U` is null by default for original native book. Evaluating a hypothetical positive U never sets native-certified true.
- `tools/test_fwn9_p9m_c18_funded_wealth_dual.py`: **12 tests** including genuinely independent 50-digit Decimal arithmetic, 1,000-term independent iterative wealth proof, conditional U monotonicity, numeric boundary/contract and invalid input controls.
- `.github/workflows/fwn9_p9m_c18.yml`: strict syntax/lint/types, tests, source hashes, M10 nonaccess, prior C17 provenance check. Initial attempt failed on unused test variable F841 and is retained; corrected CI success is audited separately.

## 5. Acceptance and next uniquely blocking proof

Do **not** consume 3,200 final M10 accounts. The new dual is a mathematically sharper baseline for self-financed execution without positive model-credit, but the original native OHLC fills can differ from the discretely available eight-step first-cross prices. We need independent, source-time evidence to upper-bound `E[U]` for the *entire original native policy and order path*, and a tighter predictable inventory `E[A]` relation using only admissible real-time information. Until both are proved and operational execution-fault and multicell requirements pass, the mathematical screen remains inconclusive and N9-S remains **NO_GO**.
