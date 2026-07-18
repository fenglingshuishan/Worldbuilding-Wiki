from __future__ import annotations

import pytest
import yaml

from worldbuilding_wiki.errors import ConflictError, ValidationError, VaultError
from worldbuilding_wiki.rendering import render_markdown
from worldbuilding_wiki.service import WorldbuildingService


def create_sample(service: WorldbuildingService) -> tuple[dict, dict]:
    world = service.info()["worlds"][0]["id"]
    location = service.create_entry(
        {
            "type": "location",
            "title": "雾港",
            "status": "canon",
            "world": world,
            "aliases": ["北方雾港"],
            "tags": ["港口"],
            "body": "终年被海雾笼罩的港口。",
        }
    )["entry"]
    character = service.create_entry(
        {
            "type": "character",
            "title": "林烬",
            "status": "canon",
            "world": world,
            "body": "出生于 [[雾港]]，也有人称它为 [[不存在的港口]]。",
            "time": {
                "display": "星历 312 年",
                "earliest_ordinal": 312,
                "latest_ordinal": 312,
            },
            "relations": [{"predicate": "born_in", "object": location["id"]}],
        }
    )["entry"]
    return location, character


def test_markdown_store_search_links_timeline_and_checks(service: WorldbuildingService) -> None:
    location, character = create_sample(service)

    search = service.list_entries(query="海雾")
    assert [item["id"] for item in search] == [location["id"]]

    detail = service.get_entry(character["id"])
    assert detail["links"][0]["target_id"] == location["id"]
    assert detail["relations"][0]["object"] == location["id"]
    assert any(item["id"] == character["id"] for item in service.timeline())

    checks = service.checks()
    assert any(item["rule_id"] == "LINK_BROKEN" for item in checks)
    assert any(item["rule_id"] == "ENTRY_ORPHAN" for item in checks) is False

    location_detail = service.get_entry(location["id"])
    assert location_detail["backlinks"][0]["id"] == character["id"]


def test_external_edit_conflict_does_not_overwrite(service: WorldbuildingService) -> None:
    _, character = create_sample(service)
    vault, _ = service.require()
    document = vault.find_entry(character["id"])
    old_hash = document.hash
    document.path.write_text(
        document.path.read_text(encoding="utf-8") + "\n外部修改。\n", encoding="utf-8"
    )

    with pytest.raises(ConflictError):
        service.update_entry(character["id"], {"title": "不应覆盖"}, old_hash)
    assert "外部修改" in document.path.read_text(encoding="utf-8")


def test_entry_history_diff_and_restore_are_recoverable(service: WorldbuildingService) -> None:
    world = service.info()["worlds"][0]["id"]
    original = service.create_entry(
        {
            "type": "concept",
            "title": "旧标题",
            "status": "draft",
            "world": world,
            "body": "第一版正文。",
        }
    )["entry"]
    second = service.update_entry(
        original["id"],
        {"title": "第二版", "status": "canon", "body": "第二版正文。"},
        original["content_hash"],
    )["entry"]
    current = service.update_entry(
        original["id"],
        {"title": "当前标题", "body": "当前正文。"},
        second["content_hash"],
    )["entry"]

    history = service.entry_history(original["id"])
    assert history["current"]["content_hash"] == current["content_hash"]
    assert [item["title"] for item in history["revisions"]] == ["第二版", "旧标题"]
    oldest_revision = history["revisions"][-1]["revision_id"]

    diff = service.entry_diff(original["id"], oldest_revision)
    assert diff["summary"]["added"] > 0
    assert diff["summary"]["deleted"] > 0
    assert any(line["kind"] == "delete" and "第一版正文" in line["text"] for line in diff["lines"])
    assert any(line["kind"] == "add" and "当前正文" in line["text"] for line in diff["lines"])

    restored = service.restore_entry(original["id"], oldest_revision, current["content_hash"])[
        "entry"
    ]
    assert restored["title"] == "旧标题"
    assert restored["status"] == "draft"
    assert restored["body"] == "第一版正文。\n"
    assert service.entry_history(original["id"])["revisions"][0]["title"] == "当前标题"


def test_invalid_time_range_is_rejected(service: WorldbuildingService) -> None:
    world = service.info()["worlds"][0]["id"]
    with pytest.raises(ValidationError, match="earliest_ordinal"):
        service.create_entry(
            {
                "type": "event",
                "title": "逆序事件",
                "status": "draft",
                "world": world,
                "time": {"earliest_ordinal": 20, "latest_ordinal": 10},
            }
        )


def test_alias_ambiguity_and_event_order_are_reported(service: WorldbuildingService) -> None:
    world = service.info()["worlds"][0]["id"]
    first = service.create_entry(
        {
            "type": "event",
            "title": "大火",
            "aliases": ["灾变"],
            "world": world,
            "time": {"earliest_ordinal": 20, "latest_ordinal": 20},
        }
    )["entry"]
    second = service.create_entry(
        {
            "type": "event",
            "title": "重建",
            "aliases": ["灾变"],
            "world": world,
            "time": {"earliest_ordinal": 10, "latest_ordinal": 10},
        }
    )["entry"]
    service.update_entry(
        first["id"],
        {"relations": [{"predicate": "causes", "object": second["id"]}]},
        first["content_hash"],
    )
    rules = {item["rule_id"] for item in service.checks()}
    assert "ALIAS_DUPLICATE" in rules
    assert "EVENT_ORDER_INVALID" in rules


def test_invalid_files_and_duplicate_ids_are_reported(service: WorldbuildingService) -> None:
    location, _ = create_sample(service)
    vault, _ = service.require()
    original = vault.find_entry(location["id"])
    duplicate = original.path.with_name("duplicate-id.md")
    duplicate.write_bytes(original.path.read_bytes())
    invalid = original.path.with_name("invalid-markdown.md")
    invalid.write_text("---\n[broken yaml\n---\n", encoding="utf-8")

    result = service.reindex()
    rules = {item["rule_id"] for item in service.checks()}
    assert result["entries"] == 2
    assert "FILE_INVALID" in rules
    assert "ID_DUPLICATE" in rules


def test_markdown_renderer_does_not_execute_raw_html() -> None:
    rendered = render_markdown("<script>alert('x')</script>\n\n[坏链接](javascript:alert(1))")
    assert "<script>" not in rendered
    assert 'href="javascript:' not in rendered


def test_platform_dashboard_templates_graph_and_bulk_workflow(
    service: WorldbuildingService,
) -> None:
    location, character = create_sample(service)

    dashboard = service.dashboard()
    assert dashboard["summary"]["entries"] == 2
    assert dashboard["summary"]["canonical"] == 2
    assert dashboard["summary"]["relations"] == 1
    assert dashboard["by_type"] == {"character": 1, "location": 1}
    assert dashboard["checks"]["warning"] >= 1

    templates = service.list_templates()
    assert any(item["id"] == "character-profile" and item["builtin"] for item in templates)
    custom = service.create_template(
        {
            "name": "章节地点",
            "description": "记录只在单章出现的重要场景。",
            "type": "location",
            "tags": ["章节场景"],
            "body": "## 场景目标\n",
        }
    )
    assert custom["builtin"] is False
    assert any(item["id"] == custom["id"] for item in service.list_templates())

    graph = service.graph_overview()
    assert {node["id"] for node in graph["nodes"]} == {location["id"], character["id"]}
    assert any(edge["label"] == "born_in" for edge in graph["edges"])

    result = service.bulk_update_entries(
        [location["id"], character["id"]], status="draft", add_tags=["第二轮"]
    )
    assert result["updated"] == 2
    assert all(item["status"] == "draft" for item in service.list_entries())
    assert all("第二轮" in item["tags"] for item in service.list_entries())

    service.delete_template(custom["id"])
    assert not any(item["id"] == custom["id"] for item in service.list_templates())


def test_template_fields_versions_and_cross_template_migration(
    service: WorldbuildingService,
) -> None:
    world = service.info()["worlds"][0]["id"]
    source = service.create_template(
        {
            "name": "城镇档案",
            "type": "location",
            "fields": [
                {"id": "population", "name": "人口", "type": "number", "required": True},
                {
                    "id": "climate",
                    "name": "气候",
                    "type": "select",
                    "options": ["寒冷", "温暖"],
                },
            ],
        }
    )
    entry = service.create_entry(
        {
            "title": "雾港",
            "type": "location",
            "world": world,
            "template_id": source["id"],
            "custom_fields": {"population": 1200, "climate": "寒冷"},
        }
    )["entry"]
    assert entry["template"] == {"id": source["id"], "version": 1}
    assert entry["custom_fields"]["population"] == 1200.0

    upgraded = service.update_template(
        source["id"],
        {
            **{
                key: source[key]
                for key in ("name", "description", "type", "status", "tags", "body")
            },
            "fields": [
                *source["fields"],
                {"id": "founded", "name": "建城年代", "type": "text"},
            ],
            "expected_version": 1,
        },
    )
    assert upgraded["version"] == 2
    vault, _ = service.require()
    assert vault.find_template_version(source["id"], 1)["fields"] == source["fields"]

    target = service.create_template(
        {
            "name": "聚落新模板",
            "type": "location",
            "fields": [
                {"id": "residents", "name": "居民数", "type": "number", "required": True},
                {"id": "notes", "name": "备注", "type": "text", "default": "待补充"},
            ],
        }
    )
    blocked = service.preview_template_migration([entry["id"]], target["id"], {})
    assert blocked["can_apply"] is False
    preview = service.preview_template_migration(
        [entry["id"]], target["id"], {"population": "residents"}
    )
    assert preview["can_apply"] is True
    assert preview["entries"][0]["custom_fields"] == {
        "residents": 1200.0,
        "notes": "待补充",
    }
    result = service.migrate_template_entries(
        [entry["id"]], target["id"], {"population": "residents"}
    )
    assert result["migrated"] == 1
    migrated = service.get_entry(entry["id"])["entry"]
    assert migrated["template"] == {"id": target["id"], "version": 1}
    assert migrated["custom_fields"]["residents"] == 1200.0
    service.delete_template(target["id"])
    assert vault.find_template_version(target["id"], 1)["fields"] == target["fields"]


def test_branch_variants_compare_and_explainable_merge(service: WorldbuildingService) -> None:
    world = service.info()["worlds"][0]["id"]
    base = service.create_entry(
        {
            "type": "event",
            "title": "王都大火",
            "world": world,
            "branch": "main",
            "body": "大火摧毁旧城。",
        }
    )["entry"]
    variant = service.create_branch_variant(base["id"], "peace-route")["entry"]
    assert variant["variant_of"] == base["id"]
    changed = service.update_entry(
        variant["id"],
        {"title": "王都和谈", "body": "大火被和谈阻止。"},
        variant["content_hash"],
    )["entry"]

    comparison = service.compare_branches("main", "peace-route")
    assert comparison["summary"]["overridden"] == 1
    assert comparison["changes"][0]["base_id"] == base["id"]
    kept = service.merge_branches("main", "peace-route", {changed["id"]: "keep_base"})
    assert kept["records"][0]["action"] == "keep_base"
    assert service.get_entry(base["id"])["entry"]["title"] == "王都大火"

    merged = service.merge_branches("main", "peace-route", {changed["id"]: "accept_target"})
    assert merged["records"][0]["base_id"] == base["id"]
    main = service.get_entry(base["id"])["entry"]
    assert main["title"] == "王都和谈"
    assert main["body"] == "大火被和谈阻止。\n"
    assert main["merge_record"]["source_id"] == changed["id"]
    assert service.compare_branches("main", "peace-route")["summary"]["synchronized"] == 1


def test_ai_scope_is_explicit_and_output_stays_in_proposal_area(
    service: WorldbuildingService,
) -> None:
    world = service.info()["worlds"][0]["id"]
    entry = service.create_entry(
        {"type": "concept", "title": "潮汐律", "world": world, "body": "每十三日倒流。"}
    )["entry"]

    class FakeSettings:
        @staticmethod
        def public_info() -> dict:
            return {
                "mode": "local",
                "enabled": True,
                "model": "test-model",
                "endpoint_origin": "http://127.0.0.1:11434",
                "has_api_key": False,
            }

    class FakeAI:
        settings = FakeSettings()

        @staticmethod
        def generate(prompt: str) -> str:
            assert "潮汐律" in prompt
            assert "每十三日倒流" in prompt
            return "建议补充倒流的能量代价。"

    service.ai = FakeAI()
    preview = service.preview_ai_scope([entry["id"]], "检查规则缺口")
    assert preview["scope"][0]["fields"] == [
        "id",
        "title",
        "type",
        "status",
        "branch",
        "tags",
        "body",
    ]
    proposal = service.generate_ai_proposal([entry["id"]], "检查规则缺口")
    assert proposal["status"] == "proposal"
    assert service.get_entry(entry["id"])["entry"]["body"] == "每十三日倒流。\n"
    assert service.list_ai_proposals()[0]["content"] == "建议补充倒流的能量代价。"
    assert service.delete_ai_proposal(proposal["id"])["deleted"] == proposal["id"]


def test_complete_sample_data_can_be_deleted_and_restored_without_touching_user_content(
    service: WorldbuildingService,
) -> None:
    assert service.sample_status()["state"] == "absent"

    restored = service.restore_sample()
    assert restored["state"] == "complete"
    assert restored["entries"] == restored["total_entries"] == 13
    sample_world = restored["world_id"]
    assert any(item["id"] == sample_world for item in service.info()["worlds"])
    assert service.list_maps(sample_world)[0]["markers"]
    assert any(item["id"] == "sample-location-record" for item in service.list_templates())
    assert service.list_entries(query="潮汐档案")[0]["id"] == "concept_5a0000000001"

    sample_entry = service.get_entry("concept_5a0000000001")["entry"]
    service.update_entry(
        sample_entry["id"],
        {"title": "被修改的示例", "body": "临时修改。"},
        sample_entry["content_hash"],
    )
    user_entry = service.create_entry(
        {
            "type": "concept",
            "title": "用户自己的内容",
            "world": sample_world,
            "body": "即使删除示例也必须保留。",
        }
    )["entry"]

    deleted = service.delete_sample()
    assert deleted["state"] == "absent"
    assert deleted["removed_entries"] == 13
    assert service.get_entry(user_entry["id"])["entry"]["title"] == "用户自己的内容"
    assert any(item["id"] == sample_world for item in service.info()["worlds"])

    service.restore_sample()
    reset_entry = service.get_entry("concept_5a0000000001")["entry"]
    assert reset_entry["title"] == "潮汐档案"
    assert len(service.list_entries(world=sample_world, limit=1000)) == 14


def test_sample_tools_refuse_unmarked_template_and_map_collisions(
    service: WorldbuildingService,
) -> None:
    restored = service.restore_sample()
    vault = service.require()[0]
    template_path = vault.root / "templates" / "sample-location-record.yaml"
    map_path = vault.root / "worlds" / restored["world_id"] / "maps" / "map_5a000000000e.yaml"
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    map_data = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    template.pop("sample_set")
    map_data.pop("sample_set")
    template_path.write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    map_path.write_text(
        yaml.safe_dump(map_data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    result = service.delete_sample()
    assert result["removed_entries"] == 13
    assert template_path.is_file()
    assert map_path.is_file()

    with pytest.raises(VaultError, match="示例模板路径已被其他内容占用"):
        service.restore_sample()
    assert service.list_entries(world=restored["world_id"], limit=1000) == []
