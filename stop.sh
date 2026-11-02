#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
exec python3 deploy/ultimate_install.py stop "$@"
