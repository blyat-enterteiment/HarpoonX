"""Private append-only decision receipts; idempotent versions, no order execution."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from ..core import digest
from .contracts import require


class Journal:
    def __init__(self, path: Path):
        self.path = path
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS receipts (account TEXT, version INTEGER, "
            "input_hash TEXT NOT NULL, receipt TEXT NOT NULL, previous TEXT NOT NULL, "
            "row_hash TEXT NOT NULL, PRIMARY KEY(account,version))"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS campaigns (account TEXT, campaign TEXT, binding TEXT NOT NULL, PRIMARY KEY(account,campaign))"
        )
        self.connection.commit()

    def append(
        self, account: str, version: int, request_hash: str, receipt: dict[str, Any]
    ) -> dict[str, Any]:
        con = self.connection
        con.execute("BEGIN IMMEDIATE")
        try:
            existing = con.execute(
                "SELECT input_hash,receipt FROM receipts WHERE account=? AND version=?",
                (account, version),
            ).fetchone()
            if existing:
                require(
                    existing[0] == request_hash,
                    "STATE_VERSION_REUSED_WITH_DIFFERENT_INPUT",
                )
                con.rollback()
                return json.loads(existing[1])
            last = con.execute(
                "SELECT version,row_hash FROM receipts WHERE account=? ORDER BY version DESC LIMIT 1",
                (account,),
            ).fetchone()
            require(last is None or version > last[0], "STALE_STATE_VERSION")
            previous = last[1] if last else "0" * 64
            prior_inventory = None
            for (old_raw,) in con.execute(
                "SELECT receipt FROM receipts WHERE account=? ORDER BY version DESC",
                (account,),
            ):
                old_receipt = json.loads(old_raw)
                if "inventory_bindings" in old_receipt:
                    prior_inventory = {
                        v["symbol"]: v["campaign_id"]
                        for v in old_receipt["inventory_bindings"]
                    }
                    break
            for binding in receipt.get("inventory_bindings", []):
                require(
                    prior_inventory is None
                    or binding["symbol"] not in prior_inventory
                    or prior_inventory[binding["symbol"]] == binding["campaign_id"],
                    "UNRECONCILED_CAMPAIGN_REPLACEMENT",
                )
                encoded = json.dumps(binding, sort_keys=True)
                prior = con.execute(
                    "SELECT binding FROM campaigns WHERE account=? AND campaign=?",
                    (account, binding["campaign_id"]),
                ).fetchone()
                require(
                    prior is None or prior[0] == encoded,
                    "CAMPAIGN_OPEN_OR_DEADLINE_CHANGED",
                )
                if prior is None:
                    con.execute(
                        "INSERT INTO campaigns VALUES(?,?,?)",
                        (account, binding["campaign_id"], encoded),
                    )
            content = json.dumps(receipt, sort_keys=True, allow_nan=False)
            row_hash = digest(
                {
                    "account": account,
                    "version": version,
                    "input_hash": request_hash,
                    "receipt": receipt,
                    "previous": previous,
                }
            )
            con.execute(
                "INSERT INTO receipts VALUES(?,?,?,?,?,?)",
                (account, version, request_hash, content, previous, row_hash),
            )
            con.commit()
            return receipt
        except Exception:
            con.rollback()
            raise

    def verify(self) -> dict[str, Any]:
        chains: dict[str, str] = {}
        count = 0
        campaigns: dict[tuple[str, str], str] = {}
        for (
            account,
            version,
            request_hash,
            raw,
            previous,
            expected,
        ) in self.connection.execute(
            "SELECT account,version,input_hash,receipt,previous,row_hash FROM receipts ORDER BY account,version"
        ):
            require(previous == chains.get(account, "0" * 64), "RECEIPT_CHAIN_BROKEN")
            actual = digest(
                {
                    "account": account,
                    "version": version,
                    "input_hash": request_hash,
                    "receipt": json.loads(raw),
                    "previous": previous,
                }
            )
            require(actual == expected, "RECEIPT_TAMPERED")
            for binding in json.loads(raw).get("inventory_bindings", []):
                key = (account, binding["campaign_id"])
                encoded = json.dumps(binding, sort_keys=True)
                require(
                    key not in campaigns or campaigns[key] == encoded,
                    "CAMPAIGN_HISTORY_CHANGED",
                )
                campaigns[key] = encoded
            chains[account] = actual
            count += 1
        stored = {
            (account, campaign): binding
            for account, campaign, binding in self.connection.execute(
                "SELECT account,campaign,binding FROM campaigns"
            )
        }
        require(campaigns == stored, "CAMPAIGN_INDEX_TAMPERED")
        return {
            "verified": True,
            "rows": count,
            "account_chains": len(chains),
            "external_authenticity": False,
            "scope": "LOCAL_HASH_CHAIN_NOT_REMOTE_ATTESTATION",
        }

    def close(self) -> None:
        self.connection.close()
