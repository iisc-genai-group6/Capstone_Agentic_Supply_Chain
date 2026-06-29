from __future__ import annotations

import os
from pathlib import Path

from agentic_scd.config import get_settings

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PACKAGE_ROOT / "assets"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def existing_path(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def config_path(name: str) -> Path:
    env_name = f"AGENTIC_SCD_{name.upper().replace('.', '_')}"
    raw = os.getenv(env_name)
    if raw:
        return Path(raw).expanduser()
    return existing_path(Path.cwd() / name, PROJECT_ROOT / name, ASSET_DIR / name)


FALLBACK_DIR = existing_path(PROJECT_ROOT / "data" / "fallback", ASSET_DIR / "fallback")
SEED_DIR = existing_path(PROJECT_ROOT / "data" / "seed", ASSET_DIR / "seed")
SOURCES_YAML = config_path("sources.yaml")
LEXICON_YAML = config_path("lexicon.yaml")
SNAPSHOT_DIR = get_settings().data_dir / "snapshots"
RUN_DIR = get_settings().data_dir / "runs"
