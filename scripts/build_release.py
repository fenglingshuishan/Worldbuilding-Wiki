#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from worldbuilding_wiki import __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a native Worldbuilding Wiki release")
    parser.add_argument("--skip-pyinstaller", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("release"))
    return parser.parse_args()


def run(command: list[str], cwd: Path) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def artifact_slug() -> str:
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
        platform.system(), platform.system().lower()
    )
    machine = platform.machine().lower()
    architecture = {
        "amd64": "x64",
        "x86_64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine, machine)
    return f"{system}-{architecture}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.skip_pyinstaller:
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--clean",
                "--noconfirm",
                "worldbuilding-wiki.spec",
            ],
            root,
        )

    distribution = root / "dist" / "WorldbuildingWiki"
    executable = distribution / (
        "WorldbuildingWiki.exe" if platform.system() == "Windows" else "WorldbuildingWiki"
    )
    if not executable.is_file():
        raise SystemExit(f"missing executable: {executable}")
    for source, destination in (
        (root / "packaging" / "README.txt", distribution / "README.txt"),
        (root / "LICENSE.txt", distribution / "LICENSE.txt"),
        (root / "CHANGELOG.md", distribution / "CHANGELOG.md"),
    ):
        shutil.copy2(source, destination)

    output = (root / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    slug = artifact_slug()
    base_name = f"Worldbuilding-Wiki-{__version__}-{slug}"
    if platform.system() == "Windows":
        archive = output / f"{base_name}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for path in sorted(distribution.rglob("*")):
                if path.is_file():
                    package.write(path, Path(base_name) / path.relative_to(distribution))
    else:
        archive = output / f"{base_name}.tar.gz"
        with tarfile.open(archive, "w:gz") as package:
            package.add(distribution, arcname=base_name, recursive=True)

    checksum = output / f"{archive.name}.sha256"
    checksum.write_text(f"{sha256(archive)}  {archive.name}\n", encoding="utf-8")
    run(
        [sys.executable, "scripts/verify_release.py", str(archive)],
        root,
    )
    print(archive)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
