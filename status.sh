#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
# Container status only; no logs, broker requests or order endpoints.
exec python3 deploy/ultimate_install.py status "$@"
