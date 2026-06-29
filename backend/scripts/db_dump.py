from __future__ import annotations

import shutil
from datetime import datetime

from _common import BACKUPS_DIR, database_path
from agentic_scd.db import init_db


def main() -> int:
    init_db()
    source = database_path()
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUPS_DIR / f"agentic-scd-{stamp}.sqlite"
    shutil.copy2(source, target)
    print(f"Wrote snapshot: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
