#!/usr/bin/env python3
"""Reconstruct the exact old measuring tree, then reproduce retained 30.16 results.

Never overlays the fixed current core. No new journal reservation or new variant.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    dest = args.workspace.resolve()
    if dest.exists():
        raise ValueError('NEW_WORKSPACE_REQUIRED')
    frozen = ROOT / 'evidence/core_quant8_30_17_0/frozen_code_30_16_0'
    shutil.copytree(frozen, dest)
    for relative in ['evidence/historical_bank_30_16_0/data', 'evidence/historical_bank_30_16_0/registration',
                     'evidence/historical_bank_30_16_0/run_completed']:
        shutil.copytree(ROOT / relative, dest / relative)
    cmd = [sys.executable, '-B', 'tools/run_historical_bank.py', '--data-dir', 'evidence/historical_bank_30_16_0/data',
           '--registration-dir', 'evidence/historical_bank_30_16_0/registration', '--output-dir', 'reproduction',
           '--verify-against', 'evidence/historical_bank_30_16_0/run_completed']
    return subprocess.run(cmd, cwd=dest, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
