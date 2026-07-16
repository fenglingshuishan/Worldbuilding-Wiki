#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

FORBIDDEN_PARTS = {
    ".env",
    ".git",
    "runtime",
    "vault",
    "vaults",
    "__pycache__",
    ".pytest_cache",
}
FORBIDDEN_SUFFIXES = {".worldvault", ".sqlite", ".db", ".log", ".pyc"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a standalone release archive")
    parser.add_argument("archive", type=Path)
    return parser.parse_args()


def extract(archive: Path, target: Path) -> None:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as package:
            package.extractall(target)
    elif archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as package:
            package.extractall(target, filter="data")
    else:
        raise SystemExit(f"unsupported archive: {archive}")


def main() -> int:
    args = parse_args()
    archive = args.archive.resolve()
    if not archive.is_file():
        raise SystemExit(f"archive not found: {archive}")
    with tempfile.TemporaryDirectory(prefix="worldwiki-release-check-") as temporary:
        root = Path(temporary)
        extract(archive, root)
        top = [path for path in root.iterdir() if path.is_dir()]
        if len(top) != 1:
            raise SystemExit("release must contain exactly one top-level directory")
        distribution = top[0]
        executable = distribution / (
            "WorldbuildingWiki.exe" if platform.system() == "Windows" else "WorldbuildingWiki"
        )
        required = [
            executable,
            distribution / "README.txt",
            distribution / "LICENSE.txt",
            distribution / "CHANGELOG.md",
        ]
        missing = [str(path.relative_to(distribution)) for path in required if not path.is_file()]
        if missing:
            raise SystemExit("missing release files: " + ", ".join(missing))
        for path in distribution.rglob("*"):
            relative = path.relative_to(distribution)
            lowered = {part.lower() for part in relative.parts}
            if lowered & FORBIDDEN_PARTS:
                raise SystemExit(f"forbidden release path: {relative}")
            if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
                raise SystemExit(f"forbidden release file: {relative}")
            if path.is_symlink():
                raise SystemExit(f"release must not contain symlinks: {relative}")
        result = subprocess.run(
            [str(executable), "--version"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if "worldbuilding-wiki 0.1.1" not in result.stdout.lower():
            raise SystemExit(f"unexpected version output: {result.stdout!r}")
        if platform.system() != "Windows" and not os.access(executable, os.X_OK):
            raise SystemExit("standalone executable is not executable")
    print(f"verified: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
