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


def test_markdown_renderer_does_not_execute_raw_html() -> None:
    rendered = render_markdown("<script>alert('x')</script>\n\n[坏链接](javascript:alert(1))")
    assert "<script>" not in rendered
    assert 'href="javascript:' not in rendered
