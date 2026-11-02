"""One read-only Alpaca data adapter with explicit feeds and bounded pagination."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core import digest, timestamp


class AlpacaData:
    HOST = "https://data.alpaca.markets"

    def __init__(
        self, key: str | None = None, secret: str | None = None, transport: Any = None
    ):
        self.key = key or os.environ.get("APCA_API_KEY_ID")
        self.secret = secret or os.environ.get("APCA_API_SECRET_KEY")
        self.transport = transport or self._get
        if not self.key or not self.secret:
            raise ValueError("ALPACA_DATA_CREDENTIALS_REQUIRED")

    def _get(self, path: str, query: dict[str, str]) -> dict[str, Any]:
        if self.key is None or self.secret is None:
            raise ValueError("ALPACA_DATA_CREDENTIALS_REQUIRED")
        request = Request(
            self.HOST + path + "?" + urlencode(query),
            headers={"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret},
            method="GET",
        )
        for attempt in range(3):
            try:
                with urlopen(request, timeout=15) as response:
                    data = response.read(20_000_001)
                    if len(data) > 20_000_000:
                        raise ValueError("DATA_RESPONSE_SIZE_BOUND")
                    return json.loads(data)
            except HTTPError as exc:
                if exc.code in (429, 502, 503, 504) and attempt < 2:
                    time.sleep(0.2 * 2**attempt)
                    continue
                raise ValueError(f"ALPACA_DATA_HTTP_{exc.code}") from None
        raise ValueError("ALPACA_DATA_UNAVAILABLE")

    def collect(
        self,
        symbols: list[str],
        kind: str,
        start: str,
        end: str,
        *,
        feed: str,
        book: str = "equity",
        max_pages: int = 30,
    ) -> dict[str, Any]:
        if (
            not 1 <= len(symbols) <= 48
            or len(set(symbols)) != len(symbols)
            or not 1 <= max_pages <= 100
            or kind not in ("quotes", "trades", "bars")
        ):
            raise ValueError("COLLECTION_BOUNDS")
        if timestamp(start) >= timestamp(end):
            raise ValueError("COLLECTION_INTERVAL")
        if (
            (book in ("equity", "etf") and feed not in ("iex", "sip"))
            or (book == "crypto" and feed != "us")
            or book not in ("equity", "etf", "crypto")
        ):
            raise ValueError("EXPLICIT_DATA_FEED")
        path = (
            "/v1beta3/crypto/us/" + kind if book == "crypto" else "/v2/stocks/" + kind
        )
        params = {
            "symbols": ",".join(symbols),
            "start": start,
            "end": end,
            "limit": "10000",
            "sort": "asc",
        }
        if book != "crypto":
            params.update(feed=feed, asof=timestamp(end).date().isoformat())
        if kind == "bars":
            params.update(timeframe="5Min" if book != "crypto" else "15Min")
            if book != "crypto":
                params["adjustment"] = "raw"
        out: dict[str, list[dict[str, Any]]] = {s: [] for s in symbols}
        tokens = set()
        pages = 0
        complete = False
        for _ in range(max_pages):
            response = self.transport(path, params.copy())
            pages += 1
            rows = response.get(kind)
            if not isinstance(rows, dict):
                raise ValueError("ALPACA_DATA_SCHEMA")
            received = datetime.now(UTC).isoformat()
            for symbol, events in rows.items():
                if symbol not in out or not isinstance(events, list):
                    raise ValueError("UNREQUESTED_SYMBOL_OR_DATA_SCHEMA")
                out[symbol].extend({**r, "known_at": received} for r in events)
            token = response.get("next_page_token")
            if not token:
                complete = True
                break
            if token in tokens:
                raise ValueError("REPEATED_DATA_PAGE_TOKEN")
            tokens.add(token)
            params["page_token"] = token
        result = {
            "origin": "OBSERVED",
            "provider": "ALPACA",
            "book": book,
            "feed": feed,
            "kind": kind,
            "start": start,
            "end": end,
            "received_at": datetime.now(UTC).isoformat(),
            "pages": pages,
            "complete": complete,
            "availability": "HISTORICAL_BACKFILL_RECEIPT_NOT_ORIGINAL_LIVE_ARRIVAL",
            kind: out,
        }
        result["content_hash"] = digest(result)
        return result
