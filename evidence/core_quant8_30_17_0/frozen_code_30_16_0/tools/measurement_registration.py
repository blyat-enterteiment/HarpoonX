"""Run the fixed local measurement reservation/verification module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "quant"))
from harpoon_quant.measurement_registration import main

if __name__ == "__main__":
    raise SystemExit(main())
