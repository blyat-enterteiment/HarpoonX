"""Synthetic ingestion/causality tests. No financial experiment, fit or broker."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_causal_panel import frame, request, write_export
from harpoon_quant.causal_panel import build, sha, verify

ROOT = Path(__file__).resolve().parents[2]
PACK = r"""
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=process.argv[1],app=process.argv[2],spec=JSON.parse(fs.readFileSync(path.join(root,'pack-input.json'),'utf8'));
const {digest}=require(path.join(app,'runtime30/ultimate_contracts.js'));
const {assemble}=require(path.join(app,'tools/export_observation_snapshot.cjs'));
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
let frames=spec.frames;
if(spec.compact_count)frames=Array.from({length:spec.compact_count},(_,i)=>{
 const now=Date.parse('2026-01-01T00:00:00Z')+i*60000;
 return {schema:'HARPOON_PROSPECTIVE_FRAME_1',account_id:'SYNTHETIC-PANEL-ACCOUNT',data_origin:'SYNTHETIC_ENGINEERING_ONLY',external_authenticity_verified:false,
 runtime_input:{now,config:{mode:'paper',expected_account_id:'SYNTHETIC-PANEL-ACCOUNT',universe:[],quoteAgeMs:5000},signals:[],market:{calendar:[],quotes:{}}},
 observation:{schema:'HARPOON_RUNTIME_OBSERVATION_1',status:'WAIT_FEATURE_DATA',asof:new Date(now).toISOString(),observations:[],rejected:{},selected:[],execution_allowed:false,liveApproved:false},financial_acceptance_allowed:false};
});
let previous='GENESIS';const records=[];
for(let i=0;i<frames.length;i++){const f=frames[i];delete f.source_frame_sha256;const h=hash(JSON.stringify(f));f.source_frame_sha256=h;const r={sequence:i+1,at:f.runtime_input.now,frame_hash:h,frame_key:'SYNTHETIC-frame-'+h,previous,stored_bytes:1};const chain_hash=digest(r);records.push({...r,chain_hash});previous=chain_hash;}
const body={schema:'HARPOON_OBSERVATION_SNAPSHOT_1',account_id:'SYNTHETIC-PANEL-ACCOUNT',configuration_hash:hash('synthetic journal'),head:previous,total_frames:frames.length,index_hash:hash('synthetic index'),captured_at:frames.at(-1).runtime_input.now+1000,execution_allowed:false,liveApproved:false},snapshot={snapshot_id:digest(body),...body};
const refs=[],size=spec.page_size||100;
for(let i=0;i<frames.length;i+=size){const chunk=frames.slice(i,i+size),name='page-'+i+'.json';const page={schema:'HARPOON_OBSERVATION_EXPORT_1',account_id:body.account_id,head:body.head,total_frames:frames.length,snapshot_id:snapshot.snapshot_id,snapshot_descriptor:body,offset:i,next_offset:i+chunk.length,frames:chunk,chain_records:records.slice(i,i+size),execution_allowed:false,liveApproved:false};const bytes=JSON.stringify(page);fs.writeFileSync(path.join(root,name),bytes);refs.push({path:name,sha256:hash(bytes)});}
const manifest=assemble(snapshot,refs,spec.selection,root);fs.writeFileSync(path.join(root,'stream-manifest.json'),JSON.stringify(manifest));
"""


class ObservationStreamTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def packed(self, frames=None, *, count=None, page_size=100):
        frames = copy.deepcopy(frames)
        if frames:
            for f in frames:
                f["runtime_input"]["config"].setdefault("universe", [{"symbol": "A", "book": "equity"}])
        (self.root / "pack-input.json").write_text(json.dumps({"frames": frames, "compact_count": count,
            "page_size": page_size, "selection": request()["selection"]}))
        subprocess.run(["node", "-e", PACK, str(self.root), str(ROOT)], check=True,
                       capture_output=True, text=True, timeout=30)
        manifest = self.root / "stream-manifest.json"
        spec = request()
        spec["observation_manifest"] = {"path": manifest.name, "sha256": sha(manifest)}
        return spec, frames

    def reseal_manifest(self, spec, change):
        file = self.root / "stream-manifest.json"
        body = json.loads(file.read_text())
        change(body)
        file.write_text(json.dumps(body))
        spec["observation_manifest"]["sha256"] = sha(file)

    def test_stream_panel_matches_complete_legacy_panel_exactly(self):
        spec, rows = self.packed([frame(0), frame(1), frame(2)], page_size=1)
        streamed = build(spec, self.root)
        original = build(request(write_export(self.root, rows)), self.root)
        self.assertEqual(streamed["panel"], original["panel"])
        self.assertEqual(streamed["counts"], original["counts"])
        self.assertEqual(streamed["rejections"], original["rejections"])
        self.assertTrue(verify(streamed, spec, self.root)["verified"])
        self.assertFalse(streamed["training_executed"])
        self.assertFalse(streamed["execution_allowed"])

    def test_more_than_twenty_thousand_frames_do_not_create_labels_or_order_authority(self):
        spec, _ = self.packed(count=20001)
        result = build(spec, self.root)
        self.assertEqual(result["counts"]["prospective_frames"], 20001)
        self.assertEqual(result["counts"]["causal_rows_admissible"], 0)
        self.assertEqual(result["panel"]["origin"], "SYNTHETIC_ENGINEERING_ONLY")
        self.assertIsNone(result["coordinator_replay_request"])
        self.assertIsNone(result["stream_processing"]["observed_retention_sessions"])

    def test_missing_page_and_resealed_manifest_cannot_hide_a_gap(self):
        spec, _ = self.packed([frame(0), frame(1), frame(2)], page_size=1)
        self.reseal_manifest(spec, lambda m: m["pages"].pop(1))
        with self.assertRaisesRegex(ValueError, "CONTINUITY"):
            build(spec, self.root)

    def test_selection_cannot_change_after_manifest_is_bound(self):
        spec, _ = self.packed([frame(0), frame(1)])
        spec["selection"]["local_time"] = "10:51"
        with self.assertRaisesRegex(ValueError, "STREAM_SELECTION_BINDING"):
            build(spec, self.root)

    def test_universe_rotation_is_causal_but_signal_configuration_change_is_rejected(self):
        rows = [frame(0), frame(1), frame(2)]
        for i, f in enumerate(rows):
            f["runtime_input"]["config"]["universe"] = [{"symbol": "A", "book": "equity"}]
            if i:
                f["runtime_input"]["config"]["universe"].append({"symbol": "NEW", "book": "etf", "discovered_at": rows[1]["runtime_input"]["now"]})
        spec, _ = self.packed(rows)
        result = build(spec, self.root)
        self.assertGreater(result["counts"]["causal_rows_admissible"], 0)
        rows[1]["runtime_input"]["config"]["slippageBps"] += 1
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            self.packed(rows)
        self.assertIn("SIGNAL_CONFIGURATION_CHANGED_SPLIT_DATASET", raised.exception.stderr)

    def test_future_discovery_is_not_adopted_as_known_universe(self):
        rows = [frame(0), frame(1)]
        rows[0]["runtime_input"]["config"]["universe"] = [{"symbol": "A", "book": "equity", "discovered_at": rows[1]["runtime_input"]["now"]}]
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            self.packed(rows)
        self.assertIn("UNIVERSE_NOT_KNOWN_AT_CAPTURE", raised.exception.stderr)

    def test_future_asset_semantics_cannot_relabel_earlier_equity_rows(self):
        rows = [frame(0), frame(1), frame(2)]
        rows[1]["runtime_input"]["market"]["assets"]["A"]["book"] = "etf"
        spec, _ = self.packed(rows)
        with self.assertRaisesRegex(ValueError, "ASSET_METADATA_SEMANTICS_CHANGED_SPLIT_DATASET"):
            build(spec, self.root)

    def test_future_factor_or_units_change_is_a_dataset_error_not_a_sampled_rejection(self):
        for key, value in (("factor", "other"), ("multiplier", 100), ("step", 0.01), ("minQty", 10)):
            with self.subTest(key=key):
                rows = [frame(0), frame(1), frame(2)]
                rows[1]["runtime_input"]["market"]["assets"]["A"][key] = value
                spec, _ = self.packed(rows)
                with self.assertRaisesRegex(ValueError, "ASSET_METADATA_SEMANTICS_CHANGED_SPLIT_DATASET"):
                    build(spec, self.root)

    def test_temporary_quote_database_is_removed_on_success_and_source_failure(self):
        spec, _ = self.packed([frame(0), frame(1)])
        temp = self.root / "temporary-quotes"
        temp.mkdir()
        with patch("harpoon_quant.causal_panel.tempfile.tempdir", str(temp)):
            build(spec, self.root)
            self.assertEqual(list(temp.iterdir()), [])
            self.reseal_manifest(spec, lambda m: m["pages"].__setitem__(0, {**m["pages"][0], "sha256": "0"*64}))
            with self.assertRaisesRegex(ValueError, "SNAPSHOT_PAGE_HASH"):
                build(spec, self.root)
            self.assertEqual(list(temp.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
