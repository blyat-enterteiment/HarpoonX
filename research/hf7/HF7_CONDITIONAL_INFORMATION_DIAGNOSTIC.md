# HF7 — Fixed conditional information test (development-only)

Date: 2026-11-18. No November 2026 or Jan-Feb 2027 data accessed. Uses archived HF5 Alpaca IEX daily bars (2025-01-02 to 2026-06-30), source Git blob 0d5df569972066272b82e00901a95282fa6e602d. 12 symbols, 10 tested names.

**Implementation:** independent JavaScript numerical logistic fit approximating HF2 regularization C=0.1; **NOT** bitwise/parity verified against sklearn. Prior-close features: previous close momentum, log(1+previous volume / 10-session prior volume), previous range/close, previous QQQ return. Positive class: next open-to-close >0. Train rows end 3 full sessions before test fold. Three fixed evaluation folds: Jan-Feb, Mar-Apr, May-Jun 2026. Baseline is training-only positive frequency. Fixed model and thresholds, no fit on evaluation labels.

| Evaluation population | N asset-days | Baseline Brier | Conditional Brier | Improvement (baseline - conditional) | Baseline log loss | Conditional log loss |
|---|---:|---:|---:|---:|---:|---:|
| All 10 assets | 1230 | 0.250093 | 0.251389 | -0.001296 | 0.693333 | 0.695967 |
| Prior-close momentum>=2%, relative volume>=1.5 | 73 | 0.249979 | 0.255026 | -0.005047 | 0.693105 | 0.703580 |
| Above plus same-day opening > previous high * 1.0025 | 18 | 0.249072 | 0.243609 | +0.005464 | 0.691292 | 0.680367 |

The 18-event apparent improvement is **not robust**: fold Brier improvement Jan-Feb +0.009443 (N=3), Mar-Apr +0.017462 (N=9), May-Jun -0.014523 (N=6). Conditional Brier is worse on the overall universe and the 73 prior-close candidate observations. Raptor open confirmation is only observable at the open, and the labels are open-to-close; the exact timing of an achievable entry is not proven. All 2026 periods are retrospectively inspected and not an untouched independent test. The universe is selected with hindsight; delisted assets and corporate actions are not reconstructed. No executable quotes, slippage or funded portfolio edge demonstrated. Small sample, cross-asset and time dependence prevent treating observations as independent.

**Decision:** reject promotion of conditional predictor; keep frozen HF2 Jan-Feb 2027 preregistration untouched. Do not change thresholds to rescue observed results. Next requirements: exact sklearn parity, independent point-in-time universe, longer train/calibration, full broker-cost execution model, block uncertainty, prospectively registered evaluation. No trades or deployment.
