#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
# .env is parsed as data by Python. Never source or eval it.
exec python3 deploy/ultimate_install.py install "$@"
