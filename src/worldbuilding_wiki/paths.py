from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "worldbuilding-wiki"


def platform_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Worldbuilding Wiki"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Worldbuilding Wiki"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_DIR_NAME


def platform_documents_dir() -> Path:
    return Path.home() / "Documents" / "Worldbuilding Wiki"


@dataclass(slots=True)
class AppPaths:
    root: Path

    @property
    def config_file(self) -> Path:
        return self.root / "config.json"

    @property
    def runtime(self) -> Path:
        return self.root / "runtime"

    @property
    def imports(self) -> Path:
        return self.runtime / "imports"

    @property
    def exports(self) -> Path:
        return self.runtime / "exports"

    @property
    def default_vaults(self) -> Path:
        return self.root / "vaults"

    def ensure(self) -> None:
        for path in (self.root, self.runtime, self.imports, self.exports, self.default_vaults):
            path.mkdir(parents=True, exist_ok=True)


class ConfigStore:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.paths.ensure()

    def read(self) -> dict:
        if not self.paths.config_file.exists():
            return {"active_vault": None, "recent_vaults": []}
        try:
            value = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"active_vault": None, "recent_vaults": []}
        value.setdefault("active_vault", None)
        value.setdefault("recent_vaults", [])
        return value

    def set_active_vault(self, path: Path) -> None:
        resolved = str(path.expanduser().resolve())
        config = self.read()
        recent = [item for item in config["recent_vaults"] if item != resolved]
        config["active_vault"] = resolved
        config["recent_vaults"] = [resolved, *recent][:10]
        self._write(config)

    def clear_active_vault(self) -> None:
        config = self.read()
        config["active_vault"] = None
        self._write(config)

    def forget_vault(self, path: Path) -> None:
        resolved = str(path.expanduser().resolve())
        config = self.read()
        if config["active_vault"] == resolved:
            config["active_vault"] = None
        config["recent_vaults"] = [item for item in config["recent_vaults"] if item != resolved]
        self._write(config)

    def _write(self, value: dict) -> None:
        target = self.paths.config_file
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, target)
