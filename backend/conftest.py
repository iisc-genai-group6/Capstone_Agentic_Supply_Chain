from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for item in (ROOT / "src", ROOT / "scripts", ROOT.parent):
    value = str(item)
    if value not in sys.path:
        sys.path.insert(0, value)
