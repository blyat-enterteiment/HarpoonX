# HF2 preregistration — prospective research, NO TRADING

Registered 2026-11-17. Historical July/August 2026 has been explored and is not pristine OOS. November 2026 remains sealed and must not be read.

## Frozen independent cohort
Evaluation window: 2027-01-04 through 2027-02-26, US regular market sessions. No model selection or parameter changes after first evaluation label. Train/calibration only from data whose outcome known at least 3 complete sessions before each fold; 3-session embargo between training and calibration. Evaluation accounts start at USD 20,000 at first session; all sessions count, including abstentions. No resetting between folds. Preserve a separate immutable model config hash before collecting data.

## Policies
CASH (zero yield for mechanical comparator), exact frozen ORIGINAL if code and provenance supplied (otherwise report NOT_AVAILABLE, never substitute a proxy), frozen Raptor proxy, HF2 logistic model. HF2 prototype settings: prior-close features [momentum, log(1+relative volume), prior range/close, prior QQQ close return], logistic L2 regularization C=0.1, fixed probability bins 0.4/0.6, minimum calibration bin sample 8, fallback to calibration distribution, mean scenario net return > 0.25%, empirical 10th percentile > -4%, 12.5 bp fee assumption per side, maximum 3 simultaneous names, 10% equity notional each, intraday next-open to next-close. No threshold tuning on evaluation dates.

## Decision and evidence
The predeclared **primary** outcome is paired difference in session log wealth increment HF2 vs CASH and HF2 vs ORIGINAL (when available), including all abstention sessions and execution costs. Secondary: HF2 vs Raptor, Brier score and reliability, max drawdown, exposure, effective sample size, sensitivity to 30 bp/side. Use chronological block bootstrap with 5-session blocks as an exploratory interval, plus full account ledger; do not promote on point estimates or classification accuracy. Declare NO_GO if primary paired lower confidence bound <=0, provenance/quotes fail, or risk/wealth invariants fail. Zero trades is a non-demonstration, not a success.

## Constraints
Data feed must be authenticated, universe constructed point-in-time including delistings, corporate actions reconciled, executable quotes and quote conditions audited, risk persistent and portfolio financed. PAPER receipts cannot substitute for real fills. Historical IEX daily OHLC is only a proxy. No broker orders or live deployment authorized.

## Limitations
This document is a preregistration plan created after previous exploratory work, not a certificate of independence or externally audited protocol. No November holdout consumed.
