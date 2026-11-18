# HF18 MNP read-only Market Data worker

This is a bounded REST collector, not a trading bot. Requires Python 3.11+ and rotated Alpaca credentials configured as APCA_API_KEY_ID and APCA_API_SECRET_KEY through a secret manager. Never commit keys. It calls only GET https://data.alpaca.markets/v2/stocks/{symbol}/{quotes|trades}. No account/order endpoints.

Run from repository root:
`python -m unittest discover -s research/hf18 -p 'test_*.py' -v`
`python research/hf18/hf18_collector.py --symbol AAPL --kind quotes --start 2026-06-15T13:30:00Z --end 2026-06-15T13:30:30Z --out /tmp/hf18_aapl_quotes`

Output includes original JSON pages and SHA-256 manifest; a failed acquisition leaves INCOMPLETE_DO_NOT_USE. A terminal next_page_token proves only that provider pagination for this query ended; IEX is partial and quotes do not certify fill eligibility. Keep all pages, do not promote to HF15 without independent quote-condition certification. In ephemeral Render instances persist output to external private storage; /tmp is not durable. No auto-deploy, no cron or public service should be enabled without explicit billing/security approval.
