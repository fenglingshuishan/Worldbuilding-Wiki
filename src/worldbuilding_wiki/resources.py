from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from worldbuilding_wiki.errors import WorldbuildingWikiError


def package_root() -> Path:
    root = Path(str(files("worldbuilding_wiki")))
    required = (
        root / "static" / "index.html",
        root / "static" / "app.css",
        root / "static" / "app.js",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise WorldbuildingWikiError(
            "应用资源不完整。已检查：" + ", ".join(str(path) for path in required)
        )
    return root


def static_dir() -> Path:
    return package_root() / "static"
