"""Render web process. Health is public; scheduling and Alpaca account access are internal."""

from __future__ import annotations

import json
import os
import threading
import time as wall
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from core import (
    ET,
    ETFS,
    FAMILIES,
    FINAL,
    PREFIX,
    START,
    UTC,
    Halt,
    Json,
    decimal,
    extend,
    frozen,
    own,
    plan,
    reconcile,
    session_bounds,
    signal,
    trade_window,
)

PAPER = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class Broker:
    def __init__(self) -> None:
        key = os.environ.get("APCA_API_KEY_ID", "").strip()
        secret = os.environ.get("APCA_API_SECRET_KEY", "").strip()
        if not key or not secret:
            raise Halt("PAPER_CREDENTIALS_MISSING")
        self.headers = {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        }
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(
        self,
        host: str,
        path: str,
        query: Json | None = None,
        method: str = "GET",
        payload: Json | None = None,
        allow_missing: bool = False,
    ) -> Any:
        if (
            host not in (PAPER, DATA)
            or not path.startswith("/")
            or path.startswith("//")
        ):
            raise Halt("DESTINATION")
        if method != "GET" and host != PAPER:
            raise Halt("PAPER_ONLY")
        url = host + path + ("?" + urllib.parse.urlencode(query) if query else "")
        req = urllib.request.Request(url, method=method, headers=self.headers)
        if payload is not None:
            req.data = json.dumps(payload).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=8) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and allow_missing:
                return None
            # Do not pass API response bodies, secrets or request headers to logs.
            raise Halt(
                ("PAPER_" if host == PAPER else "DATA_") + "HTTP_" + str(exc.code)
            ) from None
        except (OSError, ValueError):
            raise Halt(("PAPER_" if host == PAPER else "DATA_") + "TRANSPORT") from None

    def account(self) -> Json:
        return self.request(PAPER, "/v2/account")

    def orders(self, now: datetime) -> list[Json]:
        start = datetime.combine(START, datetime.min.time(), ET).astimezone(UTC)
        if now < start:
            return []

        def fetch(a: datetime, b: datetime) -> list[Json]:
            query = {
                "status": "all",
                "symbols": ",".join(ETFS),
                "direction": "asc",
                "limit": 500,
                "after": a.isoformat(),
                "until": b.isoformat(),
            }
            page = self.request(PAPER, "/v2/orders", query)
            if not isinstance(page, list):
                raise Halt("ORDER_HISTORY_FORMAT")
            if len(page) < 500:
                return page
            if b - a < timedelta(seconds=2):
                raise Halt("ORDER_HISTORY_INCOMPLETE")
            mid = a + (b - a) / 2
            return fetch(a, mid + timedelta(microseconds=1)) + fetch(
                mid - timedelta(microseconds=1), b
            )

        by_id = {
            o["id"]: o for o in fetch(start, now.astimezone(UTC) + timedelta(seconds=2))
        }
        return list(by_id.values())

    def lookup(self, cid: str) -> Json | None:
        return self.request(
            PAPER,
            "/v2/orders:by_client_order_id",
            {"client_order_id": cid},
            allow_missing=True,
        )

    def place(self, intent: Json, opening: datetime, closing: datetime) -> Json:
        cid = intent["client_order_id"]
        if not cid.startswith(PREFIX) or intent["symbol"] not in ETFS:
            raise Halt("UNIVERSE")
        existing = self.lookup(cid)
        if existing is not None:
            return self.verify(intent, existing)
        clock = self.request(PAPER, "/v2/clock")
        now = datetime.now(ET)
        stamp = datetime.fromisoformat(clock["timestamp"]).astimezone(ET)
        if (
            not clock["is_open"]
            or abs((now - stamp).total_seconds()) > 30
            or not trade_window(now, opening, closing)
            or not trade_window(stamp, opening, closing)
        ):
            raise Halt("OUTSIDE_OPENING_WINDOW")
        try:
            accepted = self.request(
                PAPER,
                "/v2/orders",
                method="POST",
                payload={
                    **intent,
                    "type": "market",
                    "time_in_force": "day",
                    "extended_hours": False,
                },
            )
        except Halt:
            # A timeout can follow acceptance. The same business key is retained on any retry.
            recovered = self.lookup(cid)
            if recovered is None:
                raise
            return self.verify(intent, recovered)
        self.verify(intent, accepted)
        confirmed = self.lookup(cid)
        if confirmed is None or confirmed.get("id") != accepted.get("id"):
            raise Halt("RECEIPT_READBACK_PENDING")
        return self.verify(intent, confirmed)

    @staticmethod
    def verify(intent: Json, receipt: Json) -> Json:
        if (
            not receipt.get("id")
            or not receipt.get("status")
            or any(
                receipt.get(k) != intent[k]
                for k in ("symbol", "side", "client_order_id")
            )
        ):
            raise Halt("BROKER_RECEIPT_MISMATCH")
        for key in ("notional", "qty"):
            if key in intent and decimal(receipt.get(key)) != decimal(intent[key]):
                raise Halt("BROKER_RECEIPT_SIZE")
        return receipt


class Runner:
    def __init__(self, broker: Broker):
        self.broker = broker
        self.seed = frozen()

    @lru_cache(maxsize=2)
    def calendar(self, day: date) -> list[Json]:
        rows = self.broker.request(
            PAPER,
            "/v2/calendar",
            {"start": self.seed["days"][-1], "end": day.isoformat()},
        )
        days = [r["date"] for r in rows]
        if not days or days[0] != self.seed["days"][-1] or days != sorted(set(days)):
            raise Halt("BROKER_CALENDAR")
        return rows

    @lru_cache(maxsize=2)
    def targets(
        self, previous: str, days: tuple[str, ...]
    ) -> tuple[list[str], dict[str, float]]:
        if previous == self.seed["days"][-1]:
            return signal(self.seed["close"])
        start = days[0] + "T00:00:00-05:00"
        end = datetime.combine(
            date.fromisoformat(previous), datetime.max.time(), ET
        ).isoformat(timespec="seconds")
        params = {
            "symbols": ",".join(x[0] for x in FAMILIES),
            "start": start,
            "end": end,
            "timeframe": "1Day",
            "feed": "sip",
            "adjustment": "split",
            "sort": "asc",
            "limit": 10000,
        }
        bars: dict[str, list[Json]] = {u: [] for u, _, _ in FAMILIES}
        seen = set()
        while True:
            result = self.broker.request(DATA, "/v2/stocks/bars", params)
            for s, rows in result.get("bars", {}).items():
                if s not in bars:
                    raise Halt("REFERENCE_UNIVERSE")
                bars[s].extend(rows)
            token = result.get("next_page_token")
            if not token:
                break
            if token in seen:
                raise Halt("MARKET_DATA_PAGINATION")
            params["page_token"] = token
            seen.add(token)
        return signal(extend(self.seed, list(days), bars))

    @lru_cache(maxsize=1)
    def assets(self, day: date) -> bool:
        for symbol in ETFS:
            asset = self.broker.request(PAPER, "/v2/assets/" + symbol)
            if (
                asset.get("symbol") != symbol
                or asset.get("status") != "active"
                or not all(asset.get(k) for k in ("tradable", "fractionable"))
            ):
                raise Halt("ASSET_NOT_AVAILABLE")
        return True

    def tick(self, now: datetime) -> tuple[str, list[Json]]:
        day = now.astimezone(ET).date()
        account = self.broker.account()
        rows = self.calendar(day)
        positions = self.broker.request(PAPER, "/v2/positions")
        history = self.broker.orders(now)
        sleeve = reconcile(account, positions, history)
        if day < START:
            return "PAPER_AUTHENTICATED_PRELAUNCH", []
        if rows[-1]["date"] != day.isoformat():
            return "MARKET_HOLIDAY", []
        self.assets(day)
        previous = rows[-2]["date"]
        active, _ = self.targets(previous, tuple(r["date"] for r in rows[:-1]))
        opening, closing = session_bounds(
            day.isoformat(), rows[-1]["open"], rows[-1]["close"]
        )
        todays = [
            o
            for o in history
            if own(o) and o["client_order_id"].startswith(f"{PREFIX}{day:%Y%m%d}-")
        ]
        if now < opening:
            return "PAPER_PREFLIGHT_READY", todays
        if not trade_window(now, opening, closing):
            pending = [o for o in todays if o["status"] not in FINAL]
            for o in pending:
                if o["status"] != "pending_cancel":
                    self.broker.request(
                        PAPER,
                        "/v2/orders/" + str(o["id"]),
                        method="DELETE",
                        allow_missing=True,
                    )
            return (
                "PAPER_CANCEL_PENDING" if pending else "RECONCILED_AFTER_WINDOW"
            ), todays
        opened = self.broker.request(
            PAPER, "/v2/orders", {"status": "open", "limit": 500}
        )
        if len(opened) >= 500 or any(not own(o) for o in opened):
            return "OTHER_OPEN_ORDERS", todays
        if opened:
            return "AWAITING_BROKER", todays
        intents = plan(sleeve, active, history, day)
        if intents:
            receipts = []
            for intent in intents:
                receipts.append(self.broker.place(intent, opening, closing))
            return "PAPER_RECEIPT_READ_BACK", receipts
        if any(
            o["status"] in ("rejected", "canceled", "expired", "replaced")
            for o in todays
        ):
            return "TERMINAL_UNFILLED_REVIEW", todays
        return (
            "PAPER_RECEIPTS_RECONCILED"
            if todays
            else "PAPER_NO_ADJUSTMENT"
            if active
            else "CASH_SIGNAL"
        ), todays


class Health(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in ("/", "/healthz"):
            self.send_error(404)
            return
        body = b'{"service":"harpoonx-etf-paper","mode":"paper","process":"up"}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        return


def worker() -> None:
    runner: Runner | None = None
    last = None
    last_log = 0.0
    while True:
        now = datetime.now(ET)
        try:
            if runner is None:
                runner = Runner(Broker())
            status, receipts = runner.tick(now)
            facts = [
                {
                    k: o.get(k)
                    for k in (
                        "id",
                        "client_order_id",
                        "symbol",
                        "side",
                        "status",
                        "filled_qty",
                        "filled_avg_price",
                    )
                }
                for o in receipts
            ]
        except Halt as exc:
            status, facts = str(exc), []
        except Exception as exc:
            status, facts = "ERROR_" + type(exc).__name__, []
        snapshot = json.dumps({"state": status, "receipts": facts}, sort_keys=True)
        if snapshot != last or wall.monotonic() - last_log > 240:
            print(
                json.dumps(
                    {
                        "at": now.isoformat(),
                        "event": "ETF_PAPER",
                        **json.loads(snapshot),
                    }
                ),
                flush=True,
            )
            last, last_log = snapshot, wall.monotonic()
        opening = now.replace(hour=9, minute=30, second=0, microsecond=0)
        remaining = (opening - now).total_seconds()
        delay = (
            3
            if -310 < remaining <= 0
            else min(60, remaining)
            if 0 < remaining <= 120
            else 60
        )
        wall.sleep(max(0.25, delay))


if __name__ == "__main__":
    frozen()
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(
        ("0.0.0.0", int(os.environ.get("PORT", "10000"))), Health
    ).serve_forever()
