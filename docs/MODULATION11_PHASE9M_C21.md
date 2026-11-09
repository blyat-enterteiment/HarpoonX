# HARPOONX — M11 / Phase 9M-C21: native OHLC structural obstruction, source-time state audit and NO_GO certificate

**VERDICT: structural non-equivalence proven under the frozen original source; no universal economic impossibility or live execution certificate. N9-S remains NO_GO, all 3,200 final M10 accounts sealed.** This C21 work creates no market seeds, strategy signals, economic accounts, orders, broker calls, deployment, merges or recursive restarts.

## 1. Theorem: OHLC-native exact eight-step first-cross equivalence is false

Original registered runtime30/profit8_replay.js (SHA256 `303aa6956cfa0a249f0432bea23894b3ee8e514c60ff011177baabc7a6974810`) checks `stopHit` from bar low/high *before* checking partial targets. STOP/TP exits are recorded with economic `at=bar.end` and informational `knownAt=bar.availableAt` (end plus 1000 ms on the original synthetic source). The separate original deterministic diagnostic runtime30/modulation11_execution_equivalence.cjs instead prices exits at the **first observed** of eight ordered substeps crossed. Both use original tick rounding, signed friction, fee per share and integer partial quantities.

### Constructive witness, zero stochastic market sampling

Opening 100 USD, high 104, low 96.40, closing 100.50; 8 long shares, entry 100, stop 98, distance 2, TP1=103, TP2=106, per-side friction .0003, commission .005/share, tick .01.

Two price sequences have exactly the SAME OHLC:

- A (TP first): 103.4, 96.4, 101, 104, 99, 98.8, 100, 100.5.
- B (STOP first): 96.4, 103.4, 101, 104, 99, 98.8, 100, 100.5.

Original native OHLC stop-first issues one STOP of 8 shares at bar.end on BOTH sequences, with 783.72 USD modeled after frictions and fees. First eight-step crossing issues TP1 of 2 then STOP of 6 on A (784.90 USD total proceeds), but STOP of 8 on B (770.92 USD). First-cross physical timestamps are t+37,500 or t+75,000 ms; native OHLC stamps the stop at t+300,000 ms. All receipts are only known by availableAt; do not treat their earlier physical timestamps as earlier cash purchasing power.

Proof by contradiction: any pure function F(OHLC,prebar_position) returns identical results for A and B. The actual ordered first-cross functions return different results. Therefore there is **no universal OHLC-only exact eight-step first-cross equivalence** for the unchanged native engine. The original WEAK source has nondegenerate Gaussian log-increments with positive joint density over neighborhoods of both positive price sequences, so this is a structural ambiguity, not a choice of external random seed. This does NOT show that a given limit price could never have transacted during a real market bar, nor that any conceivable trading policy is universally unprofitable.

## 2. Second non-identifiability: historic compact no-fill record is not the prebar policy state

A separate zero-new-seed counterexample exhibits two possible prior stops, 99.50 and 98.00, with identical historical no-fill bar and identical external OHLC record. A subsequent bar with low 99.00 activates the tighter stop but not the looser one. Thus the compact *observed no-fill row alone* cannot identify a unique conditional next-bar trigger distribution. The deterministic full frozen source and complete earlier policy information could resolve it; this does **not** claim the mathematical law is intrinsically unknowable.

An **independent local read-only audit** opened exactly one previously executed, SHA-verified original M9 development member, `evidence/modulation9/development/WEAK_730101.json.gz`, from user's ZIP of SHA256 `a1d7a78c81f16b357a8699369fa1c8ac66e2b48e90d33f0770ebad88e3e0fc92`, member SHA256 `4c45a1177a063ae4b7758ef3a644c9dbc1c1c3925d30a15d0a152f392adde819`. It read **78 old accounts**, **1,213 old trades**, **1,641 old exit fills** and no final member. The old fills comprise 1,002 STOP, 336 TP1, 92 TP2, 205 TIME and 6 MODULATION9_STALLED. Accordingly **1,430 already-recorded barrier fills** require prebar state and order-execution provenance for an original population-level conditional U argument.

Compacted original historical trade/exit-fill records include booked timestamps, reason, realized price and quantity, but omit the *time-indexed prebar* stop, TP levels, target remaining quantities, pending-stop knownAt, per-decision original IOC state/reservation snapshots and actual broker exchange execution depth/queue receipts. These are absences of the **compact archive**, not proof the values cannot be derived through a separately proved observation of the full original engine.

Local JSON evidence: `C21_WEAK_development_prebar_state_provenance.json` SHA256 `405d8fcd08d92b0ca59dfeeb5c59f518e5e50bc7142a41bcc9219f369897fc88`. The original ZIP and final accounts are not copied into GitHub. The source auditor is `tools/fwn9_p9m_c21_archived_prebar_audit.py` and must be supplied the original ZIP to reproduce byte-backed checks; GitHub CI checks the auditor's static/negative contracts, not the private ZIP bytes.

## 3. Population expectation and N9-S math status

Existing conditional C20 theorem remains useful for its restricted model: if K72=2506.7342217702894, and B is E_WEAK sum of **actual financially admitted** buy notionals, then E_WEAK[A] <= K72 B under the original 72h calendar and long predictably financed assumptions. C20 gives an event-specific Gaussian upper function U_bar(stop_before_bar,targets_before_bar,q_before_bar,source_sigma). It is **not** the unconditional numerical E_WEAK[U] for the original full native policy without the joint distribution of those prebar states.

For the original nominal 1bp/calendar-day hurdle and minimum calendar cost, the sufficient economic exclusion screen remains

    gamma * K72 * B_upper + U_upper - C_min < 355.1158528283328 USD

with gamma=expm1(0.000025*1.1/8), C_min 176 USD nominal / 352 USD stress. If U_upper=0 only as an explicit counterfactual, the B_upper ceiling is about 61,636 USD nominal or 82,061 USD stress. The historical 78 accounts from ONE development seed provide neither an independently certified B_upper nor U_upper. **Those missing values must remain null, never default to zero or fitted one-seed means.**

Even with arbitrary supplied numerical upper guesses and proof flags, the C21 gate refuses to promote original OHLC→first-cross exact equivalence: that statement is structurally false. A broker-reachable alternative would require separately documented time-resolved executable quotes/queue or authentic verified trade receipts and a changed execution policy; a broker fill cannot be proved solely from synthetic OHLC or an eight-price mark tape. Changing this original fill mapping would be a NEW execution study, not retroactive certification of M9/M10.

## 4. Executed validators and limits

GitHub [C21 CI run 42628632602](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42628632602) PASS: **15 structural source-equivalence/clock/gate tests**, **six Python archived-source rejection tests**, C20 **15 analytic** and **six native IOC** regressions, C16 **11 source-ledger** regressions and independent Decimal46 with C15 null-population handoff. Python Ruff/mypy strict, Node static checks and frozen source SHA256 all PASS. No repository original trading source changed.

**What has NOT been certified:** (a) exact executable/broker equivalence (refuted as a universal identity for original OHLC), (b) full source-time stopped/target/reservation state distribution under original WEAK, (c) numeric and tight E_WEAK total admissions bound, (d) E_WEAK of original policy event-conditioned execution credit, (e) operational partial/reject/outage/impact/multicell controls, or (f) a universal theorem of economic impossibility for all conceivable strategies. All six remain blockers, not passed checkboxes.

**Final: N9-S NO_GO.** All 3,200 M10 final accounts sealed; zero new signals, seeds, economic accounts, orders, deploys, merges and recursive research starts.
