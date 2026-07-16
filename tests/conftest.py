from __future__ import annotations

from pathlib import Path

import pytest

from worldbuilding_wiki.paths import AppPaths
from worldbuilding_wiki.service import WorldbuildingService


@pytest.fixture
def service(tmp_path: Path) -> WorldbuildingService:
    paths = AppPaths(tmp_path / "app-data")
    instance = WorldbuildingService(paths)
    instance.create_vault("测试世界库", "云海世界", tmp_path / "vault")
    return instance
