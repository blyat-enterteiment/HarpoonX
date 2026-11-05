"""Core and actual Node-to-Python worker integration; no broker access."""

from __future__ import annotations

import copy
import gzip
import json
import os
import subprocess
import sys
import unittest
from datetime import UTC, datetime
from decimal import Context, localcontext
from pathlib import Path

from harpoon_quant.compound import BOOKS
from harpoon_quant.framework import evaluate, loads
from harpoon_quant.swing_evidence import verify_account

ROOT = Path(__file__).resolve().parents[2]


def packet(operation, payload):
    return {
        "schema": "HARPOON_QUANT_FRAMEWORK_1",
        "operation": operation,
        "payload": payload,
    }


class FrameworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = ROOT / "evidence/compound_swing"
        accounts = {
            s: {
                b: json.loads(
                    gzip.decompress(
                        (directory / (s + "_" + b + ".json.gz")).read_bytes()
                    )
                )
                for b in BOOKS
            }
            for s in ("NOMINAL", "STRESS")
        }
        cls.history = packet(
            "QUALIFY_HISTORY",
            {
                "origin": "HISTORICAL_MODELED",
                "accounts": accounts,
                "dividend_symbols": {},
            },
        )

    def test_core_reconstructs_all_eight_accounts(self):
        result = evaluate(self.history)
        self.assertEqual(len(result["ledger_audit"]), 8)
        self.assertEqual(result["status"], "REJECT")
        self.assertEqual(result["selected"], [])
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["source_authenticity_verified"])
        self.assertEqual(result["result"]["gate_counts"], {"FAIL": 3, "BLOCKED": 5})

    def test_actual_python_cli_and_node_worker_equal_core(self):
        body = json.dumps(self.history)
        expected = evaluate(self.history)
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "quant"),
            "OPENBLAS_NUM_THREADS": "1",
        }
        node = "const fs=require('node:fs');require('./runtime/quant_bridge.cjs').framework(JSON.parse(fs.readFileSync(0,'utf8')),{timeoutMs:30000}).then(r=>process.stdout.write(JSON.stringify(r)));"
        commands = [
            [sys.executable, "-B", "-m", "harpoon_quant", "framework"],
            ["node", "-e", node],
        ]
        for command in commands:
            with self.subTest(command=command[0]):
                result = subprocess.run(
                    command,
                    input=body,
                    text=True,
                    capture_output=True,
                    cwd=ROOT,
                    env=env,
                    timeout=40,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

                def compare(actual, target, path="receipt"):
                    if isinstance(target, dict):
                        self.assertEqual(set(actual), set(target), path)
                        for key, value in target.items():
                            compare(actual[key], value, path + "." + key)
                    elif isinstance(target, list):
                        self.assertEqual(len(actual), len(target), path)
                        for index, value in enumerate(target):
                            compare(actual[index], value, path + "." + str(index))
                    else:
                        self.assertEqual(actual, target, path)

                compare(json.loads(result.stdout), expected)

    def test_ledger_rejects_hidden_cash_change_and_cursor_rewind(self):
        for field in ("cash", "cursor", "mark", "fee"):
            a = copy.deepcopy(self.history["payload"]["accounts"]["NOMINAL"]["JOINT"])
            if field == "cash":
                a["curve"][0]["cash"] += 1
            elif field == "cursor":
                a["curve"][1]["event_count"] = -1
            elif field == "mark":
                next(r for r in a["curve"] if r["positions"])["positions"][0][
                    "mark"
                ] = 0
            else:
                next(e for e in a["events"] if e["kind"] == "BUY")["fee"] = -1
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_account(a)

    def test_decimal_context_cannot_change_reconciliation(self):
        a = self.history["payload"]["accounts"]["NOMINAL"]["JOINT"]
        expected = verify_account(a)
        with localcontext(Context(prec=8)):
            self.assertEqual(verify_account(a), expected)

    def test_rejects_unauthenticated_live_claim_and_loose_fields(self):
        p = copy.deepcopy(self.history)
        p["payload"]["origin"] = "OBSERVED_LIVE"
        with self.assertRaisesRegex(ValueError, "MODELED_HISTORY"):
            evaluate(p)
        p = copy.deepcopy(self.history)
        p["execution_allowed"] = True
        with self.assertRaisesRegex(ValueError, "FRAMEWORK_FIELDS"):
            evaluate(p)

    def test_all_books_are_mandatory(self):
        p = copy.deepcopy(self.history)
        del p["payload"]["accounts"]["STRESS"]["CRYPTO"]
        with self.assertRaisesRegex(ValueError, "FOUR_FUNDED"):
            evaluate(p)

    def test_strict_json_and_structured_cli_error(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b"[]"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                loads(raw)
        result = subprocess.run(
            [sys.executable, "-B", "-m", "harpoon_quant", "framework"],
            input='{"schema":1,"schema":2}',
            text=True,
            capture_output=True,
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": "quant"},
            timeout=15,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["reason"], "DUPLICATE_FRAMEWORK_JSON_KEY"
        )

    def test_purge_is_reachable_from_core_packet(self):
        result = evaluate(
            packet(
                "PURGE_LABELS",
                {
                    "labels": [
                        {
                            "at": "2025-01-01T00:00Z",
                            "label_end": "2025-01-03T00:00Z",
                            "known_at": "2025-01-03T00:00Z",
                        }
                    ],
                    "test_start": "2025-01-07T00:00Z",
                },
            )
        )
        self.assertEqual(result["result"]["training_indices"], [0])
        self.assertEqual(result["selected"], [])

    def test_technical_sector_signal_is_research_only(self):
        from test_technical_swing import market

        data = market()
        second = copy.deepcopy(data["series"][-1])
        second["symbol"] = "SECOND"
        data["series"].append(second)
        at = data["sessions"][20]["open"] + 3601000
        snapshots = [
            dict(
                effective_at="1970-01-01T00:00Z",
                received_at="1970-01-01T00:00Z",
                valid_until="1970-02-01T00:00Z",
                references={"A": "SECTOR", "B": "SECOND"},
            )
        ]
        result = evaluate(
            packet(
                "TECHNICAL_SWING",
                dict(
                    dataset=data,
                    snapshots=snapshots,
                    asof=datetime.fromtimestamp(at / 1000, UTC).isoformat(),
                ),
            )
        )
        self.assertEqual(result["result"]["confirmed"]["symbol"], "A")
        self.assertEqual(result["selected"], [])
        self.assertFalse(result["execution_allowed"])

    def test_order_cost_path_keeps_unfilled_opportunity_separate(self):
        at = "2025-01-01T00:00Z"
        order = dict(
            order_id="O",
            symbol="AAPL",
            book="equity",
            side="buy",
            quantity=10,
            decision_at=at,
            quote_at=at,
            quote_received_at=at,
            terminal_at=at,
            valuation_at=at,
            bid=99,
            ask=101,
            valuation_mid=102,
        )
        result = evaluate(
            packet(
                "ORDER_COSTS",
                dict(
                    schema="HARPOON_OBSERVED_FILLS_1",
                    mode="PAPER",
                    available_at=at,
                    orders=[order],
                    fills=[],
                ),
            )
        )
        self.assertEqual(result["result"]["orders"][0]["missed_opportunity_usd"], 20)
        self.assertFalse(result["execution_allowed"])
