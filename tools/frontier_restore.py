"""Restore the complete causal dataset/model from hash-checked archived shards."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "quant"))
from harpoon_quant.core import digest
from harpoon_quant.frontier.contracts import require
from harpoon_quant.frontier.paths import price_sample
from harpoon_quant.frontier_core import write_json


def restore(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    index = json.loads((directory / "dataset_index.json").read_text())
    samples = []
    for shard in index["shards"]:
        path = (directory / shard["path"]).resolve()
        require(path.is_relative_to(directory.resolve()), "SHARD_PATH_ESCAPE")
        encoded = path.read_bytes()
        require(
            hashlib.sha256(encoded).hexdigest() == shard["gzip_sha256"],
            "SHARD_GZIP_HASH",
        )
        raw = gzip.decompress(encoded)
        require(
            hashlib.sha256(raw).hexdigest() == shard["json_sha256"], "SHARD_JSON_HASH"
        )
        samples.extend(json.loads(raw))
    dataset = {**index["dataset_metadata"], "samples": samples}
    require(digest(dataset) == index["dataset_hash"], "RESTORED_DATASET_HASH")
    metadata = json.loads((directory / "model_metadata.json").read_text())
    by_id = {r["id"]: r for r in samples}
    require(len(by_id) == len(samples), "DUPLICATE_RESTORED_CASE")
    model = {
        **metadata["model"],
        "samples": [by_id[i] for i in metadata["training_case_ids"]],
    }
    if model.get("forecast_basis") == "PRICE_PATH_ONLY":
        model["samples"] = [price_sample(row) for row in model["samples"]]
    require(
        digest({k: v for k, v in model.items() if k != "model_hash"})
        == model["model_hash"],
        "RESTORED_MODEL_HASH",
    )
    return dataset, model


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--dataset-output", type=Path, required=True)
    p.add_argument("--model-output", type=Path, required=True)
    args = p.parse_args()
    dataset, model = restore(args.directory)
    write_json(args.dataset_output, dataset)
    write_json(args.model_output, model)
