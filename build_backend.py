from __future__ import annotations

import base64
import hashlib
import tarfile
import tempfile
import textwrap
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
SRC_ROOT = ROOT / "backend" / "src"
if not SRC_ROOT.exists():
    SRC_ROOT = ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "agentic_scd"


def _load_project() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle).get("project", {})


def _dist_name(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")


def _wheel_file_name(project: dict) -> str:
    return f"{_dist_name(project['name'])}-{project['version']}-py3-none-any.whl"


def _dist_info(project: dict) -> str:
    return f"{_dist_name(project['name'])}-{project['version']}.dist-info"


def _metadata(project: dict) -> str:
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {project['name']}",
        f"Version: {project['version']}",
        f"Summary: {project.get('description', '')}",
        f"Requires-Python: {project.get('requires-python', '>=3.11')}",
    ]
    for dependency in project.get("dependencies", []):
        lines.append(f"Requires-Dist: {dependency}")
    for extra, dependencies in project.get("optional-dependencies", {}).items():
        lines.append(f"Provides-Extra: {extra}")
        for dependency in dependencies:
            lines.append(f"Requires-Dist: {dependency}; extra == '{extra}'")
    lines.append("Description-Content-Type: text/markdown")
    lines.append("")
    readme = ROOT / project.get("readme", "README.md")
    if readme.exists():
        lines.append(readme.read_text(encoding="utf-8"))
    return "\n".join(lines) + "\n"


def _wheel_metadata() -> str:
    return textwrap.dedent(
        """
        Wheel-Version: 1.0
        Generator: agentic-scd-build-backend
        Root-Is-Purelib: true
        Tag: py3-none-any
        """
    ).strip() + "\n"


def _entry_points(project: dict) -> str:
    scripts = project.get("scripts", {})
    if not scripts:
        return ""
    lines = ["[console_scripts]"]
    for name in sorted(scripts):
        lines.append(f"{name} = {scripts[name]}")
    return "\n".join(lines) + "\n"


def _hash_record(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}", str(len(data))


def _write_metadata_dir(target: Path, project: dict) -> str:
    dist_info = _dist_info(project)
    dist_info_dir = target / dist_info
    dist_info_dir.mkdir(parents=True, exist_ok=True)
    (dist_info_dir / "METADATA").write_text(_metadata(project), encoding="utf-8")
    (dist_info_dir / "WHEEL").write_text(_wheel_metadata(), encoding="utf-8")
    entry_points = _entry_points(project)
    if entry_points:
        (dist_info_dir / "entry_points.txt").write_text(entry_points, encoding="utf-8")
    return dist_info


def _package_files() -> list[Path]:
    if not PACKAGE_ROOT.exists():
        raise RuntimeError(f"package directory not found: {PACKAGE_ROOT}")
    files = []
    for path in PACKAGE_ROOT.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            files.append(path)
    return sorted(files)


def _module_files() -> list[tuple[str, Path]]:
    candidates = [ROOT / "send_synthetic_event.py", ROOT / "scripts" / "send_synthetic_event.py"]
    for path in candidates:
        if path.exists():
            return [("send_synthetic_event.py", path)]
    return []


def _editable_paths() -> str:
    paths = [SRC_ROOT, ROOT, ROOT / "scripts"]
    unique = []
    for path in paths:
        if path.exists() and path not in unique:
            unique.append(path)
    return "\n".join(str(path) for path in unique) + "\n"


def _write_wheel(wheel_directory: str, editable: bool = False) -> str:
    project = _load_project()
    wheel_name = _wheel_file_name(project)
    dist_info = _dist_info(project)
    wheel_path = Path(wheel_directory) / wheel_name
    records: list[tuple[str, str, str]] = []

    def add_bytes(archive: zipfile.ZipFile, arcname: str, data: bytes) -> None:
        archive.writestr(arcname, data)
        digest, size = _hash_record(data)
        records.append((arcname, digest, size))

    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as archive:
        if editable:
            pth_name = f"{_dist_name(project['name'])}.pth"
            add_bytes(archive, pth_name, _editable_paths().encode("utf-8"))
        else:
            for path in _package_files():
                arcname = path.relative_to(SRC_ROOT).as_posix()
                add_bytes(archive, arcname, path.read_bytes())
            for arcname, path in _module_files():
                add_bytes(archive, arcname, path.read_bytes())
        add_bytes(archive, f"{dist_info}/METADATA", _metadata(project).encode("utf-8"))
        add_bytes(archive, f"{dist_info}/WHEEL", _wheel_metadata().encode("utf-8"))
        entry_points = _entry_points(project)
        if entry_points:
            add_bytes(archive, f"{dist_info}/entry_points.txt", entry_points.encode("utf-8"))
        record_name = f"{dist_info}/RECORD"
        record_rows = [f"{name},{digest},{size}" for name, digest, size in records]
        record_rows.append(f"{record_name},,")
        archive.writestr(record_name, "\n".join(record_rows) + "\n")
    return wheel_name


def get_requires_for_build_wheel(config_settings=None) -> list[str]:
    return []


def get_requires_for_build_editable(config_settings=None) -> list[str]:
    return []


def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings=None) -> str:
    return _write_metadata_dir(Path(metadata_directory), _load_project())


def prepare_metadata_for_build_editable(metadata_directory: str, config_settings=None) -> str:
    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def build_wheel(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    return _write_wheel(wheel_directory, editable=False)


def build_editable(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    return _write_wheel(wheel_directory, editable=True)


def build_sdist(sdist_directory: str, config_settings=None) -> str:
    project = _load_project()
    base = f"{project['name']}-{project['version']}"
    target = Path(sdist_directory) / f"{base}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp) / base
        tmp_root.mkdir()
        for path in ROOT.rglob("*"):
            if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts:
                rel = path.relative_to(ROOT)
                dest = tmp_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(path.read_bytes())
        with tarfile.open(target, "w:gz") as archive:
            archive.add(tmp_root, arcname=base)
    return target.name
