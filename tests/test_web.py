from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from worldbuilding_wiki.paths import AppPaths
from worldbuilding_wiki.service import WorldbuildingService
from worldbuilding_wiki.web import create_app


def request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_first_run_create_edit_search_and_export(tmp_path: Path) -> None:
    service = WorldbuildingService(AppPaths(tmp_path / "app-data"))
    app = create_app(service)

    health = request(app, "GET", "/api/health")
    assert health.status_code == 200
    assert health.json()["ready"] is False
    shell = request(app, "GET", "/")
    assert "创作中枢" in shell.text
    assert 'id="action-dialog"' in shell.text
    assert 'id="sidebar-scrim"' in shell.text
    assert shell.headers["cache-control"] == "no-store"
    frontend = request(app, "GET", "/assets/app.js")
    assert frontend.headers["cache-control"] == "no-store"
    assert "示例全套数据" in frontend.text
    assert 'api("/api/sample/restore"' in frontend.text
    assert 'api("/api/sample", {method:"DELETE"})' in frontend.text
    assert "router().catch(renderStartupError)" in frontend.text
    assert 'link.setAttribute("aria-disabled"' in frontend.text
    assert "请先创建、打开或导入一个世界库" in frontend.text
    assert 'api("/api/vaults/current"' in frontend.text
    assert "永久删除当前世界库" in frontend.text
    assert "confirmAction" in frontend.text
    assert 'api("/api/dashboard")' in frontend.text
    assert "BLUEPRINTS" in frontend.text
    assert "KNOWLEDGE GRAPH" in frontend.text
    assert 'api("/api/entries/bulk"' in frontend.text
    assert "HISTORY" in frontend.text
    assert "/history" in frontend.text
    assert 'api("/api/maps")' in frontend.text
    assert 'class="map-marker"' in frontend.text
    assert 'setAttribute("aria-current", "page")' in frontend.text
    assert "prompt(" not in frontend.text
    stylesheet = request(app, "GET", "/assets/app.css")
    assert ".sidebar nav a.disabled" in stylesheet.text
    assert ".map-canvas" in stylesheet.text
    assert "prefers-reduced-motion" in stylesheet.text
    assert "@keyframes orbit-spin" in stylesheet.text
    sample_map = request(app, "GET", "/assets/sample-tidal-map.webp")
    assert sample_map.status_code == 200
    assert sample_map.headers["content-type"] == "image/webp"
    assert sample_map.content.startswith(b"RIFF")

    created = request(
        app,
        "POST",
        "/api/vaults",
        json={"name": "接口世界库", "world_name": "镜海", "path": str(tmp_path / "vault")},
    )
    assert created.status_code == 200
    sample = request(app, "GET", "/api/sample")
    assert sample.json()["state"] == "complete"
    assert sample.json()["entries"] == 13
    deleted_sample = request(app, "DELETE", "/api/sample")
    assert deleted_sample.json()["state"] == "absent"
    assert deleted_sample.json()["removed_entries"] == 13
    restored_sample = request(app, "POST", "/api/sample/restore")
    assert restored_sample.json()["state"] == "complete"
    world = created.json()["worlds"][0]["id"]
    second_world = request(app, "POST", "/api/worlds", json={"name": "另一重天"})
    assert second_world.status_code == 200

    entry = request(
        app,
        "POST",
        "/api/entries",
        json={
            "type": "concept",
            "title": "潮汐律",
            "status": "canon",
            "world": world,
            "tags": ["自然规则"],
            "body": "镜海每十三日倒流一次。",
        },
    )
    assert entry.status_code == 200
    entry_data = entry.json()["entry"]
    assert (
        request(app, "GET", "/api/entries", params={"q": "十三日"}).json()[0]["id"]
        == entry_data["id"]
    )

    asset = request(
        app,
        "POST",
        "/api/assets",
        params={"world": world, "filename": "世界地图.png"},
        content=b"fake-png-for-route-test",
    )
    assert asset.status_code == 200
    asset_data = asset.json()
    served = request(app, "GET", f"/api/vault-assets/{asset_data['vault_path']}")
    assert served.content == b"fake-png-for-route-test"

    updated = request(
        app,
        "PUT",
        f"/api/entries/{entry_data['id']}",
        json={
            "type": "concept",
            "title": "潮汐定律",
            "status": "canon",
            "world": world,
            "body": "新的正文。",
            "expected_hash": entry_data["content_hash"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["entry"]["title"] == "潮汐定律"

    history = request(app, "GET", f"/api/entries/{entry_data['id']}/history")
    assert history.status_code == 200
    assert history.json()["revisions"][0]["title"] == "潮汐律"
    revision_id = history.json()["revisions"][0]["revision_id"]
    diff = request(
        app,
        "GET",
        f"/api/entries/{entry_data['id']}/diff",
        params={"revision_id": revision_id},
    )
    assert diff.status_code == 200
    assert diff.json()["summary"]["added"] > 0
    stale_restore = request(
        app,
        "POST",
        f"/api/entries/{entry_data['id']}/restore",
        json={"revision_id": revision_id, "expected_hash": "0" * 64},
    )
    assert stale_restore.status_code == 409
    restored = request(
        app,
        "POST",
        f"/api/entries/{entry_data['id']}/restore",
        json={
            "revision_id": revision_id,
            "expected_hash": updated.json()["entry"]["content_hash"],
        },
    )
    assert restored.status_code == 200
    assert restored.json()["entry"]["title"] == "潮汐律"

    export = request(
        app,
        "POST",
        "/api/export/worldvault",
        json={"scope": "vault", "world_ids": []},
    )
    assert export.status_code == 200
    assert export.content.startswith(b"PK")

    receiving_service = WorldbuildingService(AppPaths(tmp_path / "receiving-app-data"))
    receiving_app = create_app(receiving_service)
    preview = request(
        receiving_app,
        "POST",
        "/api/import/preview",
        params={"mode": "new", "new_vault_name": "接口迁移目标"},
        content=export.content,
    )
    assert preview.status_code == 200
    committed = request(
        receiving_app,
        "POST",
        f"/api/import/{preview.json()['token']}/commit",
        json={"conflict_choices": {}},
    )
    assert committed.status_code == 200
    assert receiving_service.list_entries(query="潮汐律")[0]["id"] == entry_data["id"]
    assert receiving_service.entry_history(entry_data["id"])["revisions"] == []


def test_api_reports_edit_conflict(tmp_path: Path) -> None:
    service = WorldbuildingService(AppPaths(tmp_path / "app-data"))
    service.create_vault("冲突测试", "主世界", tmp_path / "vault")
    app = create_app(service)
    world = service.info()["worlds"][0]["id"]
    entry = request(
        app,
        "POST",
        "/api/entries",
        json={"type": "concept", "title": "原名", "world": world},
    ).json()["entry"]
    document = service.require()[0].find_entry(entry["id"])
    document.path.write_text(
        document.path.read_text(encoding="utf-8") + "\n外部内容", encoding="utf-8"
    )

    response = request(
        app,
        "PUT",
        f"/api/entries/{entry['id']}",
        json={
            "type": "concept",
            "title": "覆盖名",
            "world": world,
            "expected_hash": entry["content_hash"],
        },
    )
    assert response.status_code == 409
    assert "重新加载" in response.json()["message"]


def test_map_workspace_keeps_image_layers_and_markers_separate(tmp_path: Path) -> None:
    service = WorldbuildingService(AppPaths(tmp_path / "app-data"))
    service.create_vault("地图测试", "主世界", tmp_path / "vault")
    app = create_app(service)
    world = service.info()["worlds"][0]["id"]
    location = request(
        app,
        "POST",
        "/api/entries",
        json={"type": "location", "title": "雾港", "world": world},
    ).json()["entry"]

    created = request(
        app,
        "POST",
        "/api/maps",
        params={"world": world, "name": "北境地图", "filename": "north.png"},
        content=b"fake-map-image",
    )
    assert created.status_code == 200
    map_data = created.json()
    assert map_data["layers"] == [{"id": "base", "name": "默认图层", "visible": True}]
    assert request(app, "GET", map_data["image_url"]).content == b"fake-map-image"

    updated = request(
        app,
        "PUT",
        f"/api/maps/{map_data['id']}",
        json={
            "layers": [
                {"id": "base", "name": "默认图层", "visible": True},
                {"id": "politics", "name": "政治", "visible": True},
            ],
            "markers": [
                {
                    "layer_id": "politics",
                    "location_id": location["id"],
                    "x": 0.25,
                    "y": 0.75,
                }
            ],
            "expected_hash": map_data["content_hash"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["markers"][0]["location_id"] == location["id"]
    assert updated.json()["markers"][0]["x"] == 0.25
    assert (tmp_path / "vault" / "worlds" / world / "maps" / f"{map_data['id']}.yaml").is_file()

    stale = request(
        app,
        "PUT",
        f"/api/maps/{map_data['id']}",
        json={"name": "不应覆盖", "expected_hash": map_data["content_hash"]},
    )
    assert stale.status_code == 409
    deleted = request(
        app,
        "DELETE",
        f"/api/maps/{map_data['id']}",
        params={"expected_hash": updated.json()["content_hash"]},
    )
    assert deleted.status_code == 200
    assert request(app, "GET", "/api/maps").json() == []


def test_delete_current_vault_requires_exact_name_and_removes_data(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "app-data")
    service = WorldbuildingService(paths)
    vault_path = tmp_path / "delete-me"
    service.create_vault("待删除世界库", "短暂世界", vault_path)
    database = service.require()[1].database
    app = create_app(service)

    rejected = request(
        app,
        "DELETE",
        "/api/vaults/current",
        json={"confirmation": "名称错误"},
    )
    assert rejected.status_code == 409
    assert vault_path.is_dir()
    assert database.is_file()

    deleted = request(
        app,
        "DELETE",
        "/api/vaults/current",
        json={"confirmation": "待删除世界库"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["ready"] is False
    assert deleted.json()["deleted_vault"] == str(vault_path)
    assert not vault_path.exists()
    assert not database.exists()
    assert service.config.read() == {"active_vault": None, "recent_vaults": []}


def test_platform_management_api(tmp_path: Path) -> None:
    service = WorldbuildingService(AppPaths(tmp_path / "app-data"))
    service.create_vault("平台接口", "镜海", tmp_path / "vault")
    app = create_app(service)
    world = service.info()["worlds"][0]["id"]
    first = request(
        app,
        "POST",
        "/api/entries",
        json={"title": "潮汐议会", "type": "organization", "world": world},
    ).json()["entry"]
    second = request(
        app,
        "POST",
        "/api/entries",
        json={"title": "回声法则", "type": "rule", "world": world},
    ).json()["entry"]

    dashboard = request(app, "GET", "/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["summary"]["entries"] == 2
    assert request(app, "GET", "/api/graph").json()["nodes"]
    assert any(item["builtin"] for item in request(app, "GET", "/api/templates").json())

    template = request(
        app,
        "POST",
        "/api/templates",
        json={"name": "自定义组织", "type": "organization", "body": "## 宗旨"},
    )
    assert template.status_code == 200
    assert template.json()["builtin"] is False

    bulk = request(
        app,
        "POST",
        "/api/entries/bulk",
        json={
            "entry_ids": [first["id"], second["id"]],
            "status": "canon",
            "add_tags": ["已审阅"],
        },
    )
    assert bulk.status_code == 200
    assert bulk.json()["updated"] == 2
    assert all(item["status"] == "canon" for item in service.list_entries())
