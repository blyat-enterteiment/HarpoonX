from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from core import (
    ET,
    ETFS,
    FAMILIES,
    START,
    D,
    Halt,
    Json,
    Sleeve,
    client_id,
    extend,
    frozen,
    plan,
    reconcile,
    session_bounds,
    signal,
    trade_window,
)
from service import DATA, PAPER, Broker, Runner


def flat() -> Sleeve:
    return reconcile({"status": "ACTIVE", "equity": "100000", "cash": "100000"}, [], [])


class SimBroker(Broker):
    def __init__(self) -> None:
        self.day = START
        self.recs: list[Json] = []
        self.pos: list[Json] = []
        self.other: list[Json] = []
        self.fail_after_post = False
        self.trashed: list[str] = []
        self.read_receipts = 0
        self.time = datetime(2026, 11, 27, 9, 30, 3, tzinfo=ET)

    def account(self) -> Json:
        return {"status": "ACTIVE", "equity": "100000", "cash": "100000"}

    def orders(self, now: datetime) -> list[Json]:
        return self.recs.copy()

    def request(
        self,
        host: str,
        path: str,
        query: Json | None = None,
        method: str = "GET",
        payload: Json | None = None,
        allow_missing: bool = False,
    ):
        if host != PAPER:
            raise AssertionError("first day must use exact frozen signal")
        if path == "/v2/account":
            return self.account()
        if path == "/v2/calendar":
            return [
                {"date": "2026-11-25", "open": "09:30", "close": "16:00"},
                {"date": "2026-11-27", "open": "09:30", "close": "13:00"},
            ]
        if path == "/v2/positions":
            return self.pos
        if path.startswith("/v2/assets/"):
            return {
                "symbol": path.split("/")[-1],
                "status": "active",
                "tradable": True,
                "fractionable": True,
            }
        if path == "/v2/clock":
            return {"is_open": True, "timestamp": self.time.isoformat()}
        if path == "/v2/orders:by_client_order_id":
            self.read_receipts += 1
            return next(
                (
                    o
                    for o in self.recs
                    if query and o["client_order_id"] == query["client_order_id"]
                ),
                None,
            )
        if path == "/v2/orders" and method == "GET":
            return [
                o for o in self.recs if o["status"] in ("new", "partially_filled")
            ] + self.other
        if path == "/v2/orders" and method == "POST" and payload:
            r = {
                **payload,
                "id": "receipt-" + payload["symbol"],
                "status": "new",
                "filled_qty": "0",
                "filled_avg_price": None,
            }
            self.recs.append(r)
            if self.fail_after_post:
                self.fail_after_post = False
                raise Halt("PAPER_TRANSPORT")
            return r
        if path.startswith("/v2/orders/") and method == "DELETE":
            self.trashed.append(path)
            return {}
        raise AssertionError(path)


class FixedDatetime(datetime):
    stamp = datetime(2026, 11, 27, 9, 30, 3, tzinfo=ET)

    @classmethod
    def now(cls, tz=None):
        return cls.stamp.astimezone(tz)


class PaperTests(unittest.TestCase):
    def test_frozen_signal_and_allocations(self):
        s = frozen()
        active, scores = signal(s["close"])
        self.assertEqual(active, ["SQQQ", "SPXS"])
        self.assertEqual(len(s["days"]), 477)
        self.assertAlmostEqual(scores["TLT"], 0.73600, places=5)
        intents = plan(flat(), active, [], START)
        self.assertEqual([o["notional"] for o in intents], ["3297.82"] * 2)
        self.assertLess(sum(D(o["notional"]) for o in intents), D("6600"))

    def test_alpaca_endpoints_and_missing_keys(self):
        self.assertEqual(PAPER, "https://paper-api.alpaca.markets")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(Halt, "PAPER_CREDENTIALS_MISSING"):
                Broker()
        with patch.dict(
            os.environ,
            {"APCA_API_KEY_ID": "test", "APCA_API_SECRET_KEY": "test"},
            clear=True,
        ):
            b = Broker()
            for host in (
                "https://api.alpaca.markets",
                "http://paper-api.alpaca.markets",
            ):
                with self.assertRaises(Halt):
                    b.request(host, "/v2/orders", method="POST")
            with self.assertRaises(Halt):
                b.request(DATA, "/v2/orders", method="POST")

    def test_holiday_and_cutoffs(self):
        open_at, close_at = session_bounds("2026-11-27", "09:30", "13:00")
        self.assertEqual(open_at.hour, 9)
        self.assertTrue(trade_window(open_at, open_at, close_at))
        self.assertFalse(
            trade_window(open_at - timedelta(seconds=1), open_at, close_at)
        )
        self.assertFalse(
            trade_window(open_at + timedelta(minutes=5), open_at, close_at)
        )
        self.assertFalse(trade_window(close_at, open_at, close_at))

    def test_funded_and_foreign_ownership(self):
        acct = {"status": "ACTIVE", "cash": "1000", "equity": "10000"}
        self.assertEqual(
            sum(
                D(o["notional"])
                for o in plan(reconcile(acct, [], []), ["SPXL", "TMF"], [], START)
            ),
            D("1000"),
        )
        pos = [{"symbol": "TMF", "side": "long", "qty": "3", "market_value": "150"}]
        with self.assertRaisesRegex(Halt, "POSITION_RECEIPTS_MISMATCH"):
            reconcile(acct, pos, [])
        owned = {
            "id": "unique",
            "client_order_id": client_id(START, "buy", "TMF"),
            "symbol": "TMF",
            "side": "buy",
            "status": "filled",
            "filled_qty": "3",
            "filled_avg_price": "40",
        }
        sleeve = reconcile(
            {"status": "ACTIVE", "equity": "100000", "cash": "80000"}, pos, [owned]
        )
        self.assertEqual((sleeve.capital, sleeve.cash), (D("20030"), D("19880")))
        order = plan(sleeve, ["SPXL"], [owned], START + timedelta(days=3))[0]
        self.assertEqual(
            (order["symbol"], order["side"], D(order["qty"])), ("TMF", "sell", D(3))
        )
        self.assertNotIn("notional", order)

    def test_sip_calendar_and_split_anchor(self):
        seed = {"days": ["2026-11-25"], "close": {s: [100.0] for s, _, _ in FAMILIES}}
        rows = [
            {"t": "2026-11-25T05:00:00Z", "c": 50.0},
            {"t": "2026-11-27T05:00:00Z", "c": 55.0},
        ]
        by = {s: rows for s, _, _ in FAMILIES}
        self.assertEqual(
            extend(seed, ["2026-11-25", "2026-11-27"], by)["QQQ"], [100.0, 110.0]
        )
        with self.assertRaises(Halt):
            extend(seed, ["2026-11-25", "2026-11-26", "2026-11-27"], by)

    @patch("service.datetime", FixedDatetime)
    def test_repeat_restart_uncertain_post_partial_then_fill(self):
        fake = SimBroker()
        fake.fail_after_post = True
        runner = Runner(fake)
        pre = FixedDatetime.stamp - timedelta(minutes=1)
        self.assertEqual(runner.tick(pre)[0], "PAPER_PREFLIGHT_READY")
        state, receipts = runner.tick(FixedDatetime.stamp)
        self.assertEqual(
            (state, len(receipts), len(fake.recs)), ("PAPER_RECEIPT_READ_BACK", 2, 2)
        )
        self.assertGreaterEqual(fake.read_receipts, 4)
        self.assertEqual(Runner(fake).tick(FixedDatetime.stamp)[0], "AWAITING_BROKER")
        record = fake.recs[0]
        record.update(status="partially_filled", filled_qty="2", filled_avg_price="20")
        fake.pos = [
            {
                "symbol": record["symbol"],
                "side": "long",
                "qty": "2",
                "market_value": "40",
            }
        ]
        self.assertEqual(runner.tick(FixedDatetime.stamp)[0], "AWAITING_BROKER")
        for i, o in enumerate(fake.recs):
            o.update(status="filled", filled_qty=str(i + 2), filled_avg_price="20")
        fake.pos = [
            {
                "symbol": o["symbol"],
                "side": "long",
                "qty": o["filled_qty"],
                "market_value": str(D(o["filled_qty"]) * 20),
            }
            for o in fake.recs
        ]
        self.assertEqual(
            Runner(fake).tick(FixedDatetime.stamp)[0], "PAPER_RECEIPTS_RECONCILED"
        )
        self.assertEqual(len(fake.recs), 2)

    @patch("service.datetime", FixedDatetime)
    def test_foreign_pending_and_cutoff_cancel_only_own(self):
        fake = SimBroker()
        fake.other = [
            {"client_order_id": "other-book", "status": "new", "id": "foreign"}
        ]
        runner = Runner(fake)
        self.assertEqual(runner.tick(FixedDatetime.stamp)[0], "OTHER_OPEN_ORDERS")
        fake.other.clear()
        runner.tick(FixedDatetime.stamp)
        fake.other.append(
            {"id": "foreign", "client_order_id": "someone_else", "status": "new"}
        )
        self.assertEqual(
            runner.tick(FixedDatetime.stamp + timedelta(minutes=6))[0],
            "PAPER_CANCEL_PENDING",
        )
        self.assertTrue(all("foreign" not in name for name in fake.trashed))
        self.assertEqual(len(fake.trashed), 2)

    def test_negative_cap_or_short_fails(self):
        with self.assertRaises(Halt):
            reconcile({"status": "ACTIVE", "cash": "0", "equity": "-5"}, [], [])
        self.assertEqual(len(ETFS), 6)
        with self.assertRaises(Halt):
            plan(flat(), ["SPXS", "SPXL"], [], START)


if __name__ == "__main__":
    unittest.main()
