# HARPOONX — M11 / Phase 9M-C20: event-triggered WEAK U and admission-funded A

**Scoped decision: research mathematics and fixed-replay source validations PASS; N9-S NO_GO.** No source market law, native execution engine, actual capital limit, accepted policy, seed, historical economic account or holdout was changed. All M10 final 3,200 accounts remain sealed.

## 1. Why C19 still could not certify N9-S

C19 demonstrated an abstract conditional inequality `E[U_close] <= beta E[A]`, beta ~0.000368219363, using the total negative variation of the eight prices **on every bar**, whether an exit was triggered or not. Native long stops and targets, however, create a modeled bar-end fill only when original completed-bar extremes cross previously determined thresholds. The original source `runtime30/profit8_replay.js` checks `stopHit` first and replaces targets with a stop exit when both barriers are reached. `at=bar.end`, `knownAt=bar.availableAt`; prices filled from OHLC thresholds are *not* proven to be achievable as a broker fill at one of the eight ordered ticks.

## 2. Event-conditioned per-bar upper for the original WEAK Gaussian law

For a funded, positive long lot `q` at the opening of one original five-minute bar, denote the eight ordered prices `P1..P8`, opening `P0`, closing `P8`, source extrema `L` and `H`. Stops `s` and targets `(t_i,q_i)` and their quantities must be F_prebar measurable, with sum(q_i)<=q and no intrabar acquisition. Original modeled positive mark credit is at most

    U_bar <= q * (min(P0,s)-P8)_+ * 1{L<=s}
             + SUM_i q_i * (t_i-P8)_+ * 1{H>=t_i}.

Because the original stop branch preempts targets, discarding its negative correlation can only **increase** this upper. Opening-time long buys and time exits have nonpositive execution credit under the original tick rounding and friction.

For one trigger `T`, K = gross prospective sale price/P0, and `X8=log(P8/P0)`,

    E[(K-exp(X8))_+ * 1_T | F_open]
      <= min( m1(K), sqrt(m2(K) * P(T|F_open)) ),

where `m1=E[(K-exp(X8))_+]`, `m2=E[(K-exp(X8))_+²]` have closed-form Gaussian lognormal put integrals. An independent Simpson integral validates both. The trigger probability is bounded by a union over original 8 Gaussian prefix crossings, **separately within the original 0.996/0.004 one-sigma/four-sigma mixture**. Drift, activity and final sigma support extrema remain frozen. Source code retains an explicit numeric tolerance disclosure: Float64 identities are not formal interval-arithmetic certification.

The total upper is quantity weighted across STOP and TP1/TP2, and then minimized with the original C19 unconditional negative-variation upper. Consequently, the new upper is **never larger** than C19 in the model class. For example only (not a historical opportunity), opening 100 USD, q=20, stop 98, target103/106, qtarget=5 each: the stop activation-probability upper is **0.00012168518032194379**, with resulting per-bar expected positive modeled credit upper **0.00221853206618606 USD**, vs the unconditioned C19 q*100*0.00294571946 ≈5.8914 USD. Distant barriers can produce sharp improvements; near barriers can make them vanish.

This is **not** a certified global numeric expectation of native U, since the historical compact trade archives do not preserve every dynamic, *pre-bar known* stop/target state. Selecting thresholds using a realized future stop or high would violate the filtration. Original M9 source fill prices still require first-cross/exchange-executable equivalence and an order/receipt-clock proof.

## 3. Original admission and 72h population exposure inequality (no continuous cap)

Every modeled native funded long entry i satisfies, when the original IOC gate and physical cash invariants apply:

    q_i * P_open_i <= q_i * P_model_fill_i <= q_i * priceCeiling_i
                    <= approvedIocNotional_i <= 0.12 * W_decision_i.

The 12% restriction is imposed *at admission*, not continuously. Subsequent appreciation and intraday gaps can violate a 12% marked-gross ratio without violating the original reservation. Let

    B = E_WEAK SUM_{all actually funded entries i} (q_i * P_model_fill_i).

Each long lot is kept no more than the original 72h calendar deadline (or less); on the registered synthetic weekday calendar an overinclusive 4 sessions *78 bars*8 substeps gives **2496** possible intraday innovations. With delta=.000025*1.1/8, mean-one overnight price transitions, no outside capital and no future information influencing the initial lot, dropping any positive-price early-exit survival indicator yields

    H72 = SUM_{j=0..2495} exp(j*delta) = 2506.7342217702894;
    **E_WEAK[A] <= H72 * B**.

Equivalently, replacing each realized actual buy notional by its approved IOC *upper* commitment yields a weaker but still valid bound in terms of expected total approved commitments. **No expected value for B is currently independently certified** for the entire original native candidate population. The bound is conditional on all source-funded paths, and cannot be filled by averages of one market seed.

For a prospective N9-S impossibility certificate, the original C15 economic test would require

    gamma * H72 * B_upper + U_upper - C_min < 355.1158528283328 USD

for independently certified WEAK expectation uppers B_upper and U_upper, where `gamma=expm1(delta)`. Under hypothetical U_upper=0 ONLY, B_upper must be below **61,636.44 USD nominal** or **82,061.38 USD stress**. These are upper-bound *screen thresholds*, not observed population facts or new capital limits.

## 4. Native execution integration and read-only archived development diagnostics

`runtime30/fwn9_p9m_c20_admission_audit.cjs` inspects the ORIGINAL native `replayFundedPortfolio` outputs (using the identical fixed pre-existing C14 engineering signal IDs, without a new market seed): source opening, physical modeled fill, approved IOC limit, reserved notional, decision-time equity, original 12% admission and 72h hold. It rejects forged fill/commitment/clock/source conditions, and returns expected-population fields **null**, not zero.

Separately, an offline read-only Python audit of the original SHA-sealed M9 WEAK_730101 member and the original C17 ordered tape re-computed original activation-credit by exit reason for 78 already executed accounts. Its results are not independent market paths and do not run accounts or signal policies.

| Descriptive per-account / source old development | Nominal (39) | Stress (39) |
|---|---:|---:|
| Mean cumulative actual modeled buy notional | 33,461.69 USD | 32,951.74 USD |
| Mean original predictable A | 12,151,698 USD-substeps | 11,747,908 USD-substeps |
| Mean original positive modeled U | 11.1141 USD | 9.6702 USD |
| Share of U from triggered STOP fills | 99.1472% | 97.4141% |
| Original triggered STOP exit fills | 503 | 499 |
| Original triggered TP1 fills | 174 | 162 |
| Original triggered TP2 fills | 48 | 44 |

The H72*mean-original-buy-notional purely **descriptive** envelope corresponds to 83.88m USD-substeps nominal / 82.60m stress, versus observed mean A 12.15m / 11.75m. It cannot become an E[A] inequality by treating one old seed as the distribution. The historical compact archive lacks original IOC commitment/decision receipt fields and all dynamic pre-bar thresholds; these remain explicit blockers, not substituted by future event labels. All original final archive members remain unopened.

## 5. Test gates and limits

GitHub [C20 CI](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42624021949) checks 15 independent math/adversarial tests (Gaussian put first/second moments versus Simpson, tail envelope over drift/vol bounds, stop-first precedence, event-gated upper <= C19, 72h kernel using independent Decimal), 6 original native IOC fixed-replay integration tests, 14 C19 moment regressions and 11 C16 native/Decimal46 regressions, Python Ruff and mypy strict and original source checks. Initial CI failures were static/format faults and are retained; final PASS does not imply universal economic certificate.

Separately, the offline audit of one already available development member passed ten local negative and consistency tests. That local audit is not represented as a GitHub CI step.

## Decision

Event-conditioned U is now a **computable conditional expectation upper function of previsible stop/target thresholds**; predictable A is linked to actual funded admissions rather than a fictitious continuous 12% cap. Two missing population inputs prevent N9-S certification: (1) independently bounded WEAK distribution of *actual source-time admitted notionals* across all original native policies, and (2) a certified distribution of prebar stop/target states, including IOC failures, partials, outages, execution-impact and first-cross price semantics. C20 does not consume M10 final holdout, choose new signals, or authorize any form of trading.

**N9-S NO_GO; all 3,200 M10 final accounts sealed; recursive search, deployment, merges and live/paper orders remain off.**
