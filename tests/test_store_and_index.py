from __future__ import annotations

import pytest

from worldbuilding_wiki.errors import ConflictError, ValidationError
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
