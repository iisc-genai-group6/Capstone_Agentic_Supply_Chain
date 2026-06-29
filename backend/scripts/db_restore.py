from __future__ import annotations

import shutil
import sys
from pathlib import Path

from _common import REPO_ROOT, database_path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python scripts/db_restore.py <snapshot.sqlite>", file=sys.stderr)
        return 2
    snapshot = Path(argv[0])
    if not snapshot.is_absolute():
        snapshot = (REPO_ROOT / snapshot).resolve()
    if not snapshot.is_file():
        print(f"error: snapshot not found: {snapshot}", file=sys.stderr)
        return 1
    target = database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot, target)
    print(f"Restored {snapshot} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
