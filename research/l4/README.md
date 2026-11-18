# L4 Alpaca IEX daily dataset

Source: Alpaca connected historical stock bars API, requested 2026-05-01 through 2026-08-31, timeframe 1Day, feed IEX. Retrieval date 2026-11-17. All 12 symbols have 84 daily bars; timestamps normalized to date. 1008 bars. Columns: symbol, date, open, high, low, close, volume, trade_count, vwap, feed.

WARNING: IEX subset, not consolidated SIP. No independent provider authentication, no exchange calendar audit, no corporate-action adjustment, no bid/ask or actual fills, no historical membership/universe provenance. CSV is exploratory and cannot certify N9 or real execution. November holdout not accessed. GitHub blob/commit IDs provide content integrity after archival but not source authenticity.

All symbols were chosen for research before the July/August evaluation, but this does not establish an ex-ante historical universe. Corporate actions and delisted constituents require separate verification.
