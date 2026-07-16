from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from worldbuilding_wiki.errors import TransferError
from worldbuilding_wiki.paths import AppPaths
from worldbuilding_wiki.service import WorldbuildingService
from worldbuilding_wiki.transfer import TransferManager


def add_entry(service: WorldbuildingService, title: str = "天穹城") -> dict:
    return service.create_entry(
        {
            "type": "location",
            "title": title,
            "status": "canon",
            "world": service.info()["worlds"][0]["id"],
            "body": "漂浮在云层之上的城市。",
        }
    )["entry"]


def test_worldvault_round_trip_to_new_device(service: WorldbuildingService, tmp_path: Path) -> None:
    entry = add_entry(service)
    service.save_asset(service.info()["worlds"][0]["id"], "地图.png", b"map-bytes")
    archive = service.export_worldvault("vault", [])
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["format_version"] == 1
        assert "checksums.sha256" in names
        assert any(name.endswith(".png") for name in names)
        assert not any("runtime" in name or ".git" in name or ".env" in name for name in names)

    receiving = WorldbuildingService(AppPaths(tmp_path / "device-b"))
    preview = receiving.preview_import(
        archive.read_bytes(), mode="new", new_vault_name="迁移后的世界库"
    )
    assert preview["incoming_entries"] == 1
    assert preview["conflicts"] == []
    result = receiving.commit_import(preview["token"], {})
    assert result["index"]["entries"] == 1
    assert receiving.get_entry(entry["id"])["entry"]["title"] == "天穹城"


def test_merge_requires_explicit_conflict_choice(
    service: WorldbuildingService, tmp_path: Path
) -> None:
    entry = add_entry(service)
    asset = service.save_asset(service.info()["worlds"][0]["id"], "旗帜.png", b"old-asset")
    baseline = service.export_worldvault("vault", []).read_bytes()
    receiving = WorldbuildingService(AppPaths(tmp_path / "device-b"))
    first = receiving.preview_import(baseline, mode="new", new_vault_name="目标")
    receiving.commit_import(first["token"], {})

    service.update_entry(
        entry["id"],
        {"title": "天穹新城", "body": "来源设备的新版本。"},
        entry["content_hash"],
    )
    (service.require()[0].root / asset["vault_path"]).write_bytes(b"new-asset")
    incoming = service.export_worldvault("vault", []).read_bytes()
    preview = receiving.preview_import(incoming, mode="merge")
    assert [item["id"] for item in preview["conflicts"]] == [entry["id"]]
    assert [item["path"] for item in preview["file_conflicts"]] == [asset["vault_path"]]

    merged = receiving.commit_import(
        preview["token"],
        {entry["id"]: "local", f"file:{asset['vault_path']}": "local"},
    )
    assert Path(merged["recovery_snapshot"]).is_file()
    assert receiving.get_entry(entry["id"])["entry"]["title"] == "天穹城"
    assert (receiving.require()[0].root / asset["vault_path"]).read_bytes() == b"old-asset"

    preview = receiving.preview_import(incoming, mode="merge")
    receiving.commit_import(
        preview["token"],
        {entry["id"]: "incoming", f"file:{asset['vault_path']}": "incoming"},
    )
    assert receiving.get_entry(entry["id"])["entry"]["title"] == "天穹新城"
    assert (receiving.require()[0].root / asset["vault_path"]).read_bytes() == b"new-asset"


def test_static_review_contains_readable_html(service: WorldbuildingService) -> None:
    entry = add_entry(service)
    archive = service.export_review()
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert "index.html" in names
        page = next(name for name in names if name.endswith(f"{entry['id']}.html"))
        assert "天穹城" in package.read(page).decode("utf-8")
        assert "只读世界观快照" in package.read("index.html").decode("utf-8")


def test_import_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.worldvault"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("../escape.txt", "bad")
        package.writestr(
            "manifest.json", json.dumps({"format": "worldbuilding-vault", "format_version": 1})
        )
        package.writestr("checksums.sha256", "")
        package.writestr("content/vault.yaml", "bad")
    manager = TransferManager(tmp_path / "imports", tmp_path / "exports")
    with pytest.raises(TransferError, match="路径不安全"):
        manager._validate_archive(archive, extract_to=tmp_path / "out")


def test_tampered_content_is_rejected(service: WorldbuildingService, tmp_path: Path) -> None:
    add_entry(service)
    original = service.export_worldvault("vault", [])
    tampered = tmp_path / "tampered.worldvault"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith("vault.yaml"):
                data += b"\n# tampered"
            target.writestr(info, data)
    manager = TransferManager(tmp_path / "imports", tmp_path / "exports")
    with pytest.raises(TransferError, match="校验和"):
        manager._validate_archive(tampered, extract_to=None)


@pytest.mark.parametrize(
    ("names", "message"),
    [
        (("content/Map.txt", "content/map.txt"), "重复路径"),
        (("content/CON.txt",), "Windows 保留名称"),
    ],
)
def test_import_rejects_cross_platform_unsafe_paths(
    tmp_path: Path, names: tuple[str, ...], message: str
) -> None:
    archive = tmp_path / "cross-platform-unsafe.worldvault"
    with zipfile.ZipFile(archive, "w") as package:
        for name in names:
            package.writestr(name, "data")
        package.writestr(
            "manifest.json", json.dumps({"format": "worldbuilding-vault", "format_version": 1})
        )
        package.writestr("checksums.sha256", "")
    manager = TransferManager(tmp_path / "imports", tmp_path / "exports")
    with pytest.raises(TransferError, match=message):
        manager._validate_archive(archive, extract_to=tmp_path / "out")


@pytest.mark.parametrize("problem", ["invalid", "duplicate"])
def test_import_rejects_invalid_or_duplicate_entries(
    service: WorldbuildingService, tmp_path: Path, problem: str
) -> None:
    entry = add_entry(service)
    vault, _ = service.require()
    original = vault.find_entry(entry["id"])
    if problem == "invalid":
        original.path.with_name("invalid.md").write_text(
            "---\n[broken yaml\n---\n", encoding="utf-8"
        )
        message = "无法解析的条目"
    else:
        shutil.copy2(original.path, original.path.with_name("duplicate.md"))
        message = "重复条目 ID"

    archive = service.export_worldvault("vault", []).read_bytes()
    receiving = WorldbuildingService(AppPaths(tmp_path / "receiving"))
    with pytest.raises(TransferError, match=message):
        receiving.preview_import(archive, mode="new", new_vault_name="新设备")
