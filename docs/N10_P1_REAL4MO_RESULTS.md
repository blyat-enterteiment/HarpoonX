# HARPOONX N10 P1 — Real SPY option quotes, Jan–Apr 2025

## Executive result

One preregistered, deterministic **retrospective** test completed successfully on the separate N10 branch. Capital $20,000; 72-hour maximum observed holding interval; one long option max; 0.25% shared loss admission; $0.65 per option leg/side, $0.01 of premium per side, and $1/calendar day fixed charge equally on all arms. The data are **historical end-of-day option bid/ask snapshots, not actual broker receipts**. This does not validate the separate European XSP engine. No orders were submitted.

Dataset: **817,348 SPY option-contract observations, 81 trading dates between January 2 and April 30, 2025**, 408,674 calls and 408,674 puts, over 120 calendar days. Publicly mirrored by `anahatsingh-ui/options-dataset-hist` at pinned Git SHA `37f6c456fe1a4775c875673fb8ef907d5cd2fd66`. Full annual original git blob `133bf1d95c3479149bf4771bc8b3fd8b625064ce`; original SHA256 `77def9302fec018a926b270841a6507bfd69a5e46b3680fbb78267f73efb611e`. Normalized Jan–Apr subset SHA256 `01162014e951b32ceacb8064596a3341c7b6e848ae7a077460e76c01930b8acf`. This is **not independently authenticated exchange data**.

| Preregistered policy | Net USD after fixed + variable costs | Relative to CASH USD | Filled / opportunities | Max EOD DD |
|:--|--:|--:|--:|--:|
| CASH | -120.00 | 0 | 0 | 0.60% |
| FOLLOW_3D | -368.85 | -248.85 | 26 / 36 | 1.84425% |
| FADE_3D | -131.90 | -11.90 | 25 / 36 | 1.38114% |
| CALL_ALWAYS | -495.60 | -375.60 | 25 / 36 | 2.478% |
| PUT_ALWAYS | -5.15 | +114.85 | 26 / 36 | 0.93958% |

PUT_ALWAYS's best observed trade is **+$168.70**. Removing it from the fixed ledger changes net from **-$5.15 to -$173.85**, i.e. **below CASH** (-$120). Its March and April monthly results are negative. It is therefore **not a defensible positive-alpha finding**, even in this retrospective dataset. Reject promotion to N10/N9-S.

## Protocol and causal rules

Unmodified preregistration: `research/n10/p1_real_2025_4months_protocol.json`. The option and momentum choice use only closing D data. The IOC conditional limit is fixed at D; entry ask tested on next session D+1; exit bid on D+2, with a maximum 72h hold. Missing/invalid exit bid is **not silently discarded**: it triggers full write-down of value to zero; 3/4/6/1 such cases were recorded for FOLLOW/FADE/CALL/PUT respectively. Intraday fills cannot be independently verified by EOD snapshots.

## Validation

- GitHub Actions SUCCESS: https://github.com/blyat-enterteiment/HarpoonX/actions/runs/43479588990
- Original annual file Git blob SHA-1 and byte count checked against GitHub's metadata, and SHA-256 recorded.
- Independent separate Decimal audit of five capital-continuous ledgers and every trade cashflow: PASS. The normalized 4-month parquet SHA-256 and CSV SHA-256 match the artifact evidence.
- Earlier build-only static failure preserved as workflow 43479380011. Subsequent run executed this one fixed market-data test; no statistical final or alpha was spent.
- Results are not a real brokerage track record, offer price guarantee, prospective OOS validation, or licence verification. Option styles differ: **SPY American/physical vs N10 European/cash**.

## Data and reproducibility

Artifact ZIP (4-month parquet, trade log, continuous daily ledger and evidence): https://github.com/blyat-enterteiment/HarpoonX/actions/runs/43479588990/artifacts/14062884905 (expires 2026-12-13). ZIP SHA256: `b815f666859e9e85ff5857cfd60897ff0f7e8c13d6d534f74552c70c1c86d32d`.

Run script `tools/n10_real_4mo.py` from this pinned branch with `pandas==2.2.3` and `pyarrow==19.0.1`. It downloads from pinned GitHub commit, verifies original blobs, filters the January–April window, executes exactly the preregistered policies, and writes deterministic CSV/JSON evidence. Automated CI should **not be rerun as new research** unless a new distinct protocol is preregistered and the attempt charged.

Cboe ETF exercise/settlement context: https://optionsfacts.cboe.com/ ; historical 4-month file provenance: https://github.com/anahatsingh-ui/options-dataset-hist . No N9 research lease or N9 program was touched, and no M10 holdout was opened.
