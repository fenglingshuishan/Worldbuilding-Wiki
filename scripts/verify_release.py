#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from worldbuilding_wiki import __version__

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


def request_json(
    url: str, *, method: str = "GET", payload: dict[str, object] | None = None
) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def smoke_test_server(executable: Path, root: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    runtime = root / "runtime"
    vault = root / "smoke-vault"
    process = subprocess.Popen(
        [
            str(executable),
            "--data-dir",
            str(runtime),
            "serve",
            "--no-browser",
            "--port",
            str(port),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise SystemExit(f"standalone server exited early: {output}")
            try:
                health = request_json(f"{base_url}/api/health")
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise SystemExit("standalone server health check timed out") from None
                time.sleep(0.25)
        if health.get("version") != __version__:
            raise SystemExit(f"unexpected health response: {health}")
        created = request_json(
            f"{base_url}/api/vaults",
            method="POST",
            payload={"name": "发行验证", "world_name": "验证世界", "path": str(vault)},
        )
        if not created.get("ready"):
            raise SystemExit(f"standalone could not create a vault: {created}")
        dashboard = request_json(f"{base_url}/api/dashboard")
        if dashboard.get("summary", {}).get("entries") != 0:
            raise SystemExit(f"unexpected dashboard response: {dashboard}")
    finally:
        if process.poll() is None:
            try:
                request_json(f"{base_url}/api/application/exit", method="POST", payload={})
                process.wait(timeout=10)
            except (urllib.error.URLError, TimeoutError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


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
        if platform.system() != "Windows" and not os.access(executable, os.X_OK):
            raise SystemExit("standalone executable is not executable")
        result = subprocess.run(
            [str(executable), "--version"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if f"worldbuilding-wiki {__version__}" not in result.stdout.lower():
            raise SystemExit(f"unexpected version output: {result.stdout!r}")
        smoke_test_server(executable, root)
    print(f"verified: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
