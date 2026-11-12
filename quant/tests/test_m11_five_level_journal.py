"""C38 private persistence, no latch reset from quote rebounds or restarts."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from harpoon_quant.five_level_guard import (
    GridSpec, Inventory, Quote, create_grid, empty_latch, inspect,
)
from harpoon_quant.five_level_journal import Writer, create, verify

AT = 1_800_000_000_000


def grid():
    return create_grid(GridSpec(
        symbol="BTC/USD", strategy="CRYPTO_BREAKOUT_RESEARCH",
        book="crypto", reference_price="100000.00", atr_closed_price="2000.00",
        spread_price="30.00", tick_size="0.01",
        entry_fee_bps="25", exit_fee_bps="25",
        other_roundtrip_friction_bps="30",
        quote_known_at_ms=AT-100, atr_known_at_ms=AT-1000,
        decision_at_ms=AT,
        original_native_prefilter_seen=True,
        provenance="SYNTHETIC_RESEARCH",
    ))


def observed(grid_, bid="98000.00"):
    quote = Quote(bid=bid, ask=bid, source_at_ms=AT-200,
                  locally_known_at_ms=AT-100, decision_at_ms=AT)
    i = Inventory(position_qty="0", actual_entry_price=None,
                  position_grid_generation=None, pending_entry_qty="0",
                  pending_entry_grid_generation=None,
                  verified_broker_snapshot=True)
    return inspect(grid_, empty_latch(grid_), quote, i,
                   c36_research_gate_passed=True,
                   existing_native_protection_present=False)[0]


class GridJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)/"private"
        self.grid = grid()
        create(self.directory, self.grid)

    def test_initial_manifest_pins_frozen_grid_and_no_trade(self):
        x = verify(self.directory, self.grid)
        self.assertEqual(x["entries"], 1)
        self.assertFalse(x["state"].veto_latched)
        self.assertFalse(x["paper_or_live_orders_allowed"])

    def test_latched_minus_two_survives_restart(self):
        w = Writer(self.directory, self.grid)
        w.append(observed(self.grid))
        persisted = w.close()
        self.assertTrue(persisted["state"].veto_latched)
        self.assertTrue(verify(self.directory, self.grid)["state"].veto_latched)
        again = Writer(self.directory, self.grid)
        self.assertTrue(again.close()["state"].veto_latched)

    def test_bounce_back_cannot_clear_persistent_stop_veto(self):
        w = Writer(self.directory, self.grid)
        w.append(observed(self.grid))
        cleared = empty_latch(self.grid)
        with self.assertRaisesRegex(ValueError, "UNAUTHORIZED_STATE_RESET"):
            w.append(replace(cleared, last_known_at_ms=AT+100))
        self.assertTrue(w.close()["state"].veto_latched)

    def test_exit_pending_unconfirmed_cannot_be_deleted_from_history(self):
        w = Writer(self.directory, self.grid)
        breached = observed(self.grid)
        w.append(replace(breached, exit_pending_unconfirmed=True))
        with self.assertRaisesRegex(ValueError, "UNAUTHORIZED_STATE_RESET"):
            w.append(replace(breached, last_known_at_ms=AT+100))
        self.assertTrue(w.close()["state"].exit_pending_unconfirmed)

    def test_same_asset_wrong_grid_generation_rejected(self):
        changed = create_grid(replace(
            self.grid.spec, reference_price="101000.00"
        ))
        with self.assertRaisesRegex(ValueError, "MANIFEST_MISMATCH"):
            verify(self.directory, changed)

    def test_tampered_price_history_bytes_detected(self):
        w = Writer(self.directory, self.grid)
        w.append(observed(self.grid))
        w.close()
        p = self.directory/"latch.ndjson"
        raw = p.read_text()
        p.write_text(raw.replace('"veto_latched": true', '"veto_latched": false'))
        with self.assertRaisesRegex(ValueError, "CHAIN_OR_SEQUENCE_TAMPER"):
            verify(self.directory, self.grid)

    def test_truncated_append_record_rejected(self):
        p = self.directory/"latch.ndjson"
        p.write_text(p.read_text()+"{\"partial\": true")
        with self.assertRaisesRegex(ValueError, "TRUNCATED_STATE_LOG"):
            verify(self.directory, self.grid)

    def test_exclusive_writer_lock_survives_interrupted_process(self):
        w = Writer(self.directory, self.grid)
        with self.assertRaisesRegex(ValueError, "STALE_LOCK"):
            Writer(self.directory, self.grid)
        w.close()

    def test_research_state_store_rejects_world_readable_file(self):
        p = self.directory/"manifest.json"
        os.chmod(p, 0o644)
        with self.assertRaisesRegex(ValueError, "PRIVATE_FILE"):
            verify(self.directory, self.grid)

    def test_private_state_store_rejects_foreign_file(self):
        (self.directory/"unknown.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_FILE"):
            verify(self.directory, self.grid)

    def test_journal_cannot_overwrite_prior_sealed_capture(self):
        with self.assertRaisesRegex(ValueError, "NEW_NONHOLDOUT"):
            create(self.directory, self.grid)

    def test_journal_will_not_operate_in_m10_holdout(self):
        d = Path(self.tmp.name)/"M10_final"
        with self.assertRaisesRegex(ValueError, "NEW_NONHOLDOUT"):
            create(d, self.grid)

    def test_grid_price_level_forgery_rejected(self):
        fake = replace(self.grid, two_levels_lower_than_reference="1.00")
        with self.assertRaisesRegex(ValueError, "GRID_LEVEL_OR_GENERATION_TAMPER"):
            verify(self.directory, fake)

    def test_writer_stops_without_hidden_broker_action(self):
        w = Writer(self.directory, self.grid)
        self.assertTrue(w.close()["local_integrity_verified"])
        self.assertFalse(verify(self.directory, self.grid)[
            "broker_source_independently_authenticated"])


if __name__ == "__main__":
    unittest.main()
