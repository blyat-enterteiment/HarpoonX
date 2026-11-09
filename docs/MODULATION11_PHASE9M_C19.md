# HARPOONX M11-C19 — Native predictable exposure A and source mark execution credit U

**Decision: N9-S NO_GO.** This is a conditional WEAK model-class proof plus an independently executed *read-only* audit of existing development records. It is not a certification that native OHLC threshold fills were tradable, nor a prospective population result. M10 final 3,200 remain sealed.

## A. Correct C17's invalid pre-step exposure upper

C15 A is the sum of q_before_step times S_before_step for every original Gaussian innovation, not q times prices AFTER each innovation. The older C17 archived-development upper summed the eight post-step prices and is NOT necessarily an upper. Example: one long share, opening 100, all eight subsequent step prices 99: correct A=100+7*99=793; prior alleged upper=8*99=792.

Rebuilding both assets on one shared chronological clock (both opening exits, both opening entries, then eight simultaneous innovations, then both closing exits), the original frozen M9 WEAK_730101 archive reports **56 of 78** previously executed accounts with A_exact > A_C17_old_upper. Old C17 archived upper MUST NOT enter C15. The separate C16 bar-high conservative envelope has a different domain and is not this incorrect sum.

## B. Exact pathwise modeled book decomposition

For native receipts under their ORIGINAL effective timestamps: A_exact=sum_asset/bar/step q_before_step*S_previous_step. Positive execution credit U=sum_fill max(Y_fill,0), with Y_buy=q*(bar_open-filled_buy), Y_open_sell=q*(filled_sell-bar_open), Y_end_sell=q*(filled_sell-bar_close). This is a mathematically exact *mark-relative credit* on source timestamp conventions; it is NOT a broker-price executable credit. The source original STOP/TP branch uses OHLC highs/lows known at bar.availableAt=end+1000ms to produce fills economically marked at bar.end.

The signed wealth ledger telescopes exactly: W_T-W_0 = intraday_inventory_price_PnL + overnight_inventory_price_PnL + signed_Y - fees - full calendar charges. Original pending closing receipts cannot be recycled for an admission before knownAt. Reconciliation is on the original already-executed development archive; no signal, seed or account is regenerated.

## C. New uniform conditional WEAK inequality

Let P0=open, P1..P8=the original registered eight prices, H=max(P0..P8), C=P8. All source-modelled bar-end long sales have total quantity no greater than the funded pre-bar lot q and native sale price not greater than H. Hence by finite negative variation:

  U_bar <= q * (H-C)_+ <= q * SUM_j max(P_(j-1)-P_j,0).

Under original WEAK Gaussian independent normal innovations, original mixture 1x (0.996) / 4x sigma (0.004), sigma-scale support, activity bound exp(0.7), drift |d_bar| <= 0.000025*1.1, and q measurable before this bar's innovation, the one-sided Gaussian put identity provides an analytic moment:

  E[U] <= kappa * E SUM_bar q*S_baropen; E[A] >= lambda_min * E SUM_bar q*S_baropen.

where kappa=0.0029457194636491974, lambda_min=sum(j=0..7) exp(-j*0.0000275/8)=7.999903750827143, yielding

  **E_WEAK[U] <= 0.0003682193630572902 * E_WEAK[A]**.

This applies to the specified funded/predictable native *source-close mark* class with no beneficial open fills; it is not a theorem about actual broker fills. It does NOT assume the original 12% reservation limit is a continuously maintained market-exposure cap.

The resulting coarse unconditional wealth tower still gives E[A] <= 2.5264107939e20 USD-substeps and E[U] <= 9.3025098892e16 USD. Its nominal expected-log upper is ~1,657.81 bp/day against N9-S hurdle 1 bp/day: economically vacuous despite being orders of magnitude smaller than the C17 global high-range envelope. Neither N9-S feasibility nor impossibility follows.

## D. Retrospective exact accounting of existing single-seed development archive

Verified original ZIP SHA256 a1d7a78c81f16b357a8699369fa1c8ac66e2b48e90d33f0770ebad88e3e0fc92 and ONLY member evidence/modulation9/development/WEAK_730101.json.gz SHA256 4c45a1177a063ae4b7758ef3a644c9dbc1c1c3925d30a15d0a152f392adde819, together with the C17 seven-decimal tape source checksum a173af77533f7bbe2b0a3ae54485ee64bc4f33cc83a01b860efdb0702d102398.

| Original previously executed account statistic (one development seed only) | Nominal 39 | Stress 39 |
|---|---:|---:|
| Mean exact native A, USD-substeps | 12,151,698.19 | 11,747,907.88 |
| Mean modeled positive U, USD | 11.11 | 9.67 |
| Mean signed modeled execution credit, USD | -15.82 | -31.28 |
| Accounts with a step exceeding 12% gross market exposure | 6 | 10 |
| Accounts ever exceeding hypothetical C18 uniform 9.6974% proof threshold | 38 | 38 |

The cash/inventory/overnight/trading-price/fees/calendar signed-wealth telescoping error is <=3.1e-13 USD across 78 existing accounts, 1,213 pre-existing trades and 1,641 pre-existing exit fills. Nine local adversarial/consistency tests passed; local evidence and runnable Python auditor are separate conversation artifacts, **not GitHub CI**. The 78 accounts share ONE WEAK seed and policies; they are not 78 independent stochastic market paths, and means are not expected-value certificates.

## E. Test evidence, unresolved proof and acceptance

GitHub Actions [C19 CI](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42571218435) passed 13 analytical/negative tests (with a subsequent explicit deterministic C17 refutation test), Ruff, strict mypy, source SHA hashes, and C16 11 fixed native regression checks with independent Decimal46 and C15 fail-closed handoff. Prior failed CI attempts are retained.

The next proof barrier is event-conditioned U, not uniform every-bar negative variation; and a population-tight predictable A conditional bound for the original signal/IOC/stop/target admission process. There is still no universal source-time, eight-step-first-cross/broker-executable fill equivalence, nor complete partial-reject-outage-impact-multicell controls. NO_GO stays enforced. No new seeds, signals, economic accounts, M10 finals, orders, deployments, merges or automation restarts.
