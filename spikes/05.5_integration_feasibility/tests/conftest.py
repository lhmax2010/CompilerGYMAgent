from __future__ import annotations

import sys
from pathlib import Path


SPIKE_DIR = Path(__file__).resolve().parents[1]
if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))
