# HARPOONX M11 9M-C17 R2 — eight-step provenance, recovered historical development book and conditional E[A/U]

**Scope:** development-only, existing M9 WEAK seed 730101; no new policies, seeds, signals, economic account executions or final M10 account opening. **N9-S: NO_GO**.

## 1. Source-recovered ordered tape

Source `quant/harpoon_quant/modulation9.py` SHA256 `9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab`; protocol SHA256 `de694919b0908fc0ecf474c9612ff7d54fe04db635a385e12ffa0f81abc7780d`. C17 traces the existing `intrabar` ndarray at the original M9 source line while using exactly the pre-registered WEAK development seed 730101. A second uninstrumented market generation in the same process matches the dataset hash; a separate program checks every recovered bar against source OHLCV. Only 126 evaluation sessions, 2 assets, 19,656 bar-asset rows, and **157,248 ordered prices** are exported. No strategy nominations are called.

### Cross-run floating-point identity correction

Two independent GitHub runners showed bit-level drift despite the same frozen source, seed and NumPy. Run `42562122895` raw tape SHA256 `e4bbbdbfdf01da49d2447d916afc2545354f36e19e572b1cd8be9748996c5717` differed from run `42562577404` SHA256 `2c90338dad770959727fe9cd0d592445987996c58acedd7ea10787b270e50e53`. The maximum observed absolute price difference was `3.410605131648481e-13` USD/share and maximum relative difference `2.8667793258782922e-15`. **Never label these two raw floats bitwise identical.**

R2 retains the exact raw price tape and raw per-run checksum; it adds an independently recomputed audit-only canonical checksum using seven decimal digits for every original price and OHLC field, preserving time and symbol. The two runs share SHA256 `a173af77533f7bbe2b0a3ae54485ee64bc4f33cc83a01b860efdb0702d102398`. The seven-decimal view is NEVER supplied to strategy or execution; it does not establish stop/target equality at a trading tick. CI also deliberately corrupts a price and checks rejection. [C17 R2 complete CI](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42562983146) passed.

## 2. Independently audited archived development accounts, not replayed

Located in the user's Library: `HarpoonX_Modulacion9_Trayectorias_Sinteticas_20261107.zip`, verified SHA256 `a1d7a78c81f16b357a8699369fa1c8ac66e2b48e90d33f0770ebad88e3e0fc92`. Opened **only** the original archive member `evidence/modulation9/development/WEAK_730101.json.gz`, member SHA256 `4c45a1177a063ae4b7758ef3a644c9dbc1c1c3925d30a15d0a152f392adde819`. Its recorded original historical full-input SHA256 is `782766fb68d0b2ce782d8bf08779415c94204e13fc7ca41308caed3b97258e46`. This covers broader historical input including signals. C17's market-only regenerated dataset is a distinct object and **does not yet cryptographically match this full-input hash**.

Using an offline read-only Python auditor in the current container (`fwn9_p9m_c17_development_archive_audit.py`), the historical development member was parsed without re-running a trading account. Original archived records contained **78 already executed accounts** (39 nominal and 39 stress), **1,213 original trades** and **1,641 original exit fills**. Per account the auditor reconstructed inventory and cash from original prices/quantities, accrued original costs as each calendar day passed, prevented unknown exit receipts from financing earlier entries, checked original lot fees, applied all original exits, reconciled terminal cash against archived curve and summary, and computed A/U pathwise bounds from the recovered original eight-step tape. All 78 accounts reconciled. Six local adversarial checks were executed and passed. This offline archive audit is **not** the same as GitHub CI; its Python script/JSON are separately provided as sandbox artifacts in the current conversation.

| Historic one-seed development median per account | Nominal | Stress |
|---|---:|---:|
| A pathwise lower, USD-substeps | 10,365,162.73 | 9,478,218.51 |
| A pathwise upper, USD-substeps | 10,604,778.74 | 9,700,057.49 |
| U pathwise upper, USD | 19.7921 | 17.2092 |

Exits are timestamped at original bar ends; their first true eight-step crossing is not inferred from retrospective OHLC. For A lower, only inventory surviving potentially intrabar exits receives the whole-bar eight-step sum; A upper assumes pre-exit shares throughout the bar. U upper uses best possible positive execution credit against actual recorded eight-step low, without asserting modeled fills are individually attainable. Some modeled prices include spread/slippage outside bar extrema (for example, buys above high or sells below low); the guard checks `entry>=opening` and `exit<=high`, not false equality of modeled fill and the tape.

**These medians do not estimate population E[A] or E[U].** They reuse the same development seed, policies and costs, with no prospective alpha. Neither the 78 accounts nor the source prices should be used for new policy selection.

## 3. Finite but vacuous expectation bounds

Under long, funded bar-open acquisitions without intrabar recycling or borrowing, causal prebar inventory, exit proceeds bounded by source eight-step high, mean-one WEAK overnight, and nonnegative costs, one-sided Gaussian moment and union bounds give `K-1=0.0060381278978958175`, `r=0.012076148699679413`, `E[A] <=1.32e33 USD-substeps`, `E[U] <=1.9806e30 USD`. These are **conditional uniform upper bounds for an abstract policy class**, not validated for every native executable path. The numerical evaluations are rounded floating point rather than computer-assisted formal interval bounds. They are orders of magnitude above the economic 1bp/day exclusion threshold and therefore DO NOT prove native infeasibility or achieve N9-S.

## 4. Gates

CI passes 8 analytic unit tests, Gaussian quadrature, strictly typed/checked new code, original source hashes, development seed whitelist, repeated source market OHLCV identity, independent 157,248-price parity, 7-decimal checksum, tamper control, C16 native 11/11 accounting regressions, independent Decimal46 C16 fixture, and guarded C15 handoff with unknown expected A and U (NOT substituted by a historical path).

Remaining: source-time proof that full native entry/partial/stop/target/IOC decisions admit an exact causal ordered-eight-step execution mapping, mathematically tight expected conditional inventory bounds, covariance/WEAK drift filtration support, re-checked historical full-input digest provenance, all execution fault/impact/multicell operational controls, and independent prospective validation. Until then **N9-S NO_GO**, no broker, no live/paper orders, no deployment, no merge or automation resume.
