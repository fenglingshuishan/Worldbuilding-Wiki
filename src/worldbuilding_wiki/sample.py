from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from worldbuilding_wiki.errors import ValidationError, VaultError
from worldbuilding_wiki.store import Vault, dump_markdown

SAMPLE_SET = "tidal-archive-v1"
SAMPLE_WORLD_ID = "tidal-archive-demo"
SAMPLE_WORLD_NAME = "潮汐档案 · 示例全套数据"
SAMPLE_TEMPLATE_ID = "sample-location-record"
SAMPLE_MAP_ID = "map_5a000000000e"
SAMPLE_MAP_FILENAME = "tidal-archive-map.webp"
SAMPLE_CREATED_AT = "2026-07-18T08:00:00+08:00"

SAMPLE_TEMPLATE = {
    "id": SAMPLE_TEMPLATE_ID,
    "sample_set": SAMPLE_SET,
    "name": "示例 · 地点观测记录",
    "description": "展示自定义字段如何与地点正文并存。",
    "type": "location",
    "status": "draft",
    "tags": ["示例全套数据", "观测"],
    "body": "## 现场印象\n\n## 可见线索\n\n## 叙事用途\n",
    "version": 1,
    "fields": [
        {
            "id": "tide-level",
            "name": "潮位等级",
            "type": "select",
            "required": True,
            "options": ["低", "中", "高"],
        },
        {
            "id": "access-risk",
            "name": "进入风险",
            "type": "number",
            "required": False,
            "options": [],
        },
        {
            "id": "open-to-public",
            "name": "对公众开放",
            "type": "boolean",
            "required": False,
            "options": [],
        },
    ],
}


def _entry(
    entry_id: str,
    entry_type: str,
    title: str,
    body: str,
    *,
    status: str = "canon",
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    relations: list[dict[str, str]] | None = None,
    time: dict[str, Any] | None = None,
    template: dict[str, Any] | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "id": entry_id,
        "type": entry_type,
        "title": title,
        "aliases": aliases or [],
        "world": SAMPLE_WORLD_ID,
        "branch": "main",
        "status": status,
        "tags": ["示例全套数据", *(tags or [])],
        "relations": relations or [],
        "sample_set": SAMPLE_SET,
        "created_at": SAMPLE_CREATED_AT,
        "updated_at": SAMPLE_CREATED_AT,
    }
    if time:
        metadata["time"] = time
    if template:
        metadata["template"] = template
        metadata["custom_fields"] = custom_fields or {}
    return {"metadata": metadata, "body": body.strip() + "\n"}


SAMPLE_ENTRIES = (
    _entry(
        "concept_5a0000000001",
        "concept",
        "潮汐档案",
        """
## 一句话

群岛每十三日经历一次海水逆流，记忆也会随潮汐留下可被读取的盐痕。

## 从这里开始

先阅读 [[回潮律]]，再沿 [[雾港]]、[[镜湖]] 与 [[琉砂原]] 查看地点、人物、事件、关系和地图如何连成一个世界。
""",
        tags=["入口", "世界概览"],
        aliases=["示例世界入口"],
        relations=[{"predicate": "related_to", "object": "rule_5a0000000002"}],
    ),
    _entry(
        "rule_5a0000000002",
        "rule",
        "回潮律",
        """
## 规则

每十三日黎明，外海潮流倒转六个小时；接触逆流的人会看见一段不属于自己的旧记忆。

## 代价

读取越久，自己的短期记忆越模糊。[[测潮钟]] 能测出安全时限，但无法阻止回潮。
""",
        tags=["核心规则", "潮汐"],
        relations=[{"predicate": "uses", "object": "artifact_5a000000000a"}],
    ),
    _entry(
        "loc_5a0000000003",
        "location",
        "雾港",
        """
## 印象

北岸港城终年被银雾包围，屋顶用旧船板拼成，码头灯在回潮前会自动熄灭。

## 叙事钩子

[[林烬]] 在这里替 [[潮汐议会]] 收集盐痕；失踪的第七码头只在逆流时出现。
""",
        tags=["港口", "北岸"],
        aliases=["北雾港"],
        relations=[{"predicate": "located_in", "object": "loc_5a000000000d"}],
        template={"id": SAMPLE_TEMPLATE_ID, "version": 1},
        custom_fields={"tide-level": "高", "access-risk": 3.0, "open-to-public": True},
    ),
    _entry(
        "loc_5a0000000004",
        "location",
        "镜湖",
        """
## 印象

群岛中央的淡水湖，水面在无风时映出未来一天的天空，却从不映出观看者本人。

## 关联

听潮人把湖心岛视为记忆的源头；[[第十三次回潮]] 后，湖底出现了通往旧王都的阶梯。
""",
        tags=["湖泊", "圣地"],
        relations=[{"predicate": "related_to", "object": "culture_5a0000000009"}],
    ),
    _entry(
        "loc_5a0000000005",
        "location",
        "琉砂原",
        """
## 印象

东部沙原由透明盐晶构成，白昼折射出多重地平线，夜晚则能听见埋藏船骸的钟声。

## 风险

强光会制造方向错觉。旅行者通常以 [[测潮钟]] 的低频振动判断真正的海岸方向。
""",
        tags=["荒原", "东境"],
        relations=[{"predicate": "uses", "object": "artifact_5a000000000a"}],
    ),
    _entry(
        "char_5a0000000006",
        "character",
        "林烬",
        """
## 身份

雾港的盐痕记录员，擅长从破损记忆中辨认地点，却逐渐忘记自己的童年。

## 当前目标

她想在下一次回潮前找到第七码头，并确认 [[雾港航志]] 中被刮去的领航者姓名。
""",
        tags=["主角", "记录员"],
        relations=[
            {"predicate": "born_in", "object": "loc_5a0000000003"},
            {"predicate": "member_of", "object": "org_5a0000000007"},
        ],
    ),
    _entry(
        "org_5a0000000007",
        "organization",
        "潮汐议会",
        """
## 职责

议会维护航道、发布回潮预警，并封存可能改变公共记忆的盐痕记录。

## 内部矛盾

公开派主张让所有人读取历史，守潮派则认为 [[第十三次回潮]] 已证明记忆必须分级管理。
""",
        tags=["治理", "派系"],
        relations=[{"predicate": "located_in", "object": "loc_5a0000000003"}],
    ),
    _entry(
        "event_5a0000000008",
        "event",
        "第十三次回潮",
        """
## 经过

逆流持续了整整一天，所有港钟同时倒转；数百人看见了旧王都沉没前的同一段记忆。

## 影响

[[潮汐议会]] 因此建立盐痕封存制度，[[镜湖]] 湖底也第一次露出石阶。
""",
        tags=["历史转折", "灾变"],
        relations=[
            {"predicate": "causes", "object": "org_5a0000000007"},
            {"predicate": "related_to", "object": "loc_5a0000000004"},
        ],
        time={"display": "群岛历 313 年霜月", "earliest_ordinal": 3130, "latest_ordinal": 3131},
    ),
    _entry(
        "culture_5a0000000009",
        "culture",
        "听潮人",
        """
## 信念

听潮人相信记忆属于海而非个人，人的一生只是替海暂存故事。

## 习俗

成年礼在 [[镜湖]] 岸边举行：参与者说出一段愿意被遗忘的往事，再把名字写进盐片沉入湖底。
""",
        tags=["文化", "仪式"],
        relations=[{"predicate": "located_in", "object": "loc_5a0000000004"}],
    ),
    _entry(
        "artifact_5a000000000a",
        "artifact",
        "测潮钟",
        """
## 外观

掌心大小的黄铜钟，没有钟舌；靠近逆流时，外壳会以骨传导方式发出低鸣。

## 限制

它只能提示记忆侵蚀的速度，不能判断看见的内容是否真实。旧型号常在 [[琉砂原]] 产生误报。
""",
        tags=["工具", "黄铜"],
        relations=[{"predicate": "related_to", "object": "rule_5a0000000002"}],
    ),
    _entry(
        "source_5a000000000b",
        "source",
        "雾港航志",
        """
## 来源

一本由历代领航员接力书写的防水册，边缘布满不同年代的盐晶。

## 争议

第十三次回潮的十二页被人为割除，仅剩一句批注：“不要让林烬听见第七码头的钟。”
""",
        tags=["史料", "线索"],
        relations=[{"predicate": "related_to", "object": "event_5a0000000008"}],
    ),
    _entry(
        "concept_5a000000000c",
        "concept",
        "第七码头假说",
        """
## 传闻

有人认为雾港存在一座只在回潮中出现的第七码头，停靠着从未发生过的历史。

## 待验证

[[林烬]] 已找到三份相互矛盾的航图；下一步需要把坐标与 [[雾港航志]] 的缺页痕迹比对。
""",
        status="rumor",
        tags=["谜团", "待验证"],
        relations=[{"predicate": "related_to", "object": "loc_5a0000000003"}],
    ),
    _entry(
        "loc_5a000000000d",
        "location",
        "风脊山",
        """
## 印象

西部山脉像折断的船骨伸向北海，是雾港抵御季风的天然屏障。

## 路径

山腰旧烽道连接 [[雾港]] 与内陆 [[镜湖]]，回潮时可避开低地盐雾，但会经过听潮人的禁声石阵。
""",
        tags=["山脉", "西境"],
        relations=[{"predicate": "related_to", "object": "loc_5a0000000003"}],
    ),
)

SAMPLE_MAP = {
    "id": SAMPLE_MAP_ID,
    "name": "潮汐群岛 · 示例地图",
    "world": SAMPLE_WORLD_ID,
    "image": f"worlds/{SAMPLE_WORLD_ID}/maps/{SAMPLE_MAP_FILENAME}",
    "layers": [
        {"id": "base", "name": "地点", "visible": True},
        {"id": "mysteries", "name": "谜团", "visible": True},
    ],
    "markers": [
        {
            "id": "marker-mistport",
            "layer_id": "base",
            "location_id": "loc_5a0000000003",
            "x": 0.28,
            "y": 0.27,
        },
        {
            "id": "marker-mirrorlake",
            "layer_id": "base",
            "location_id": "loc_5a0000000004",
            "x": 0.53,
            "y": 0.49,
        },
        {
            "id": "marker-glassplain",
            "layer_id": "base",
            "location_id": "loc_5a0000000005",
            "x": 0.75,
            "y": 0.61,
        },
        {
            "id": "marker-windspine",
            "layer_id": "base",
            "location_id": "loc_5a000000000d",
            "x": 0.35,
            "y": 0.55,
        },
        {
            "id": "marker-seventhpier",
            "layer_id": "mysteries",
            "location_id": "loc_5a0000000003",
            "x": 0.18,
            "y": 0.18,
        },
    ],
    "sample_set": SAMPLE_SET,
    "created_at": SAMPLE_CREATED_AT,
    "updated_at": SAMPLE_CREATED_AT,
}


def sample_status(vault: Vault) -> dict[str, Any]:
    installed_entries = 0
    for item in SAMPLE_ENTRIES:
        path = _entry_path(vault, item)
        if path.is_file():
            try:
                document = vault.read_path(path)
            except (OSError, UnicodeDecodeError, ValidationError):
                continue
            if document.metadata.get("sample_set") == SAMPLE_SET:
                installed_entries += 1
    template_exists = _has_sample_marker(vault.root / "templates" / f"{SAMPLE_TEMPLATE_ID}.yaml")
    map_exists = _has_sample_marker(
        vault.root / "worlds" / SAMPLE_WORLD_ID / "maps" / f"{SAMPLE_MAP_ID}.yaml"
    )
    total = len(SAMPLE_ENTRIES)
    if installed_entries == total and template_exists and map_exists:
        state = "complete"
    elif installed_entries or template_exists or map_exists:
        state = "partial"
    else:
        state = "absent"
    return {
        "id": SAMPLE_SET,
        "name": SAMPLE_WORLD_NAME,
        "state": state,
        "installed": state == "complete",
        "entries": installed_entries,
        "total_entries": total,
        "world_id": SAMPLE_WORLD_ID,
        "map_id": SAMPLE_MAP_ID if map_exists else None,
    }


def restore_sample(vault: Vault, map_source: Path) -> dict[str, Any]:
    world_root = vault.root / "worlds" / SAMPLE_WORLD_ID
    world_file = world_root / "world.yaml"
    template_path = vault.root / "templates" / f"{SAMPLE_TEMPLATE_ID}.yaml"
    map_root = world_root / "maps"
    map_path = map_root / f"{SAMPLE_MAP_ID}.yaml"
    image_path = map_root / SAMPLE_MAP_FILENAME
    if not map_source.is_file():
        raise VaultError(f"内置示例地图缺失：{map_source}")
    map_bytes = map_source.read_bytes()

    # Validate every fixed destination before writing anything. A collision must
    # leave the vault untouched instead of producing a partially restored sample.
    if world_file.exists():
        value = yaml.safe_load(world_file.read_text(encoding="utf-8")) or {}
        if value.get("sample_set") != SAMPLE_SET:
            raise VaultError(f"世界 ID 已被非示例内容占用：{SAMPLE_WORLD_ID}")
    for item in SAMPLE_ENTRIES:
        path = _entry_path(vault, item)
        if path.exists():
            document = vault.read_path(path)
            if document.metadata.get("sample_set") != SAMPLE_SET:
                raise VaultError(f"条目 ID 已被非示例内容占用：{item['metadata']['id']}")
    if template_path.exists():
        value = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
        if value.get("id") != SAMPLE_TEMPLATE_ID or value.get("sample_set") != SAMPLE_SET:
            raise VaultError("示例模板路径已被其他内容占用")
    if map_path.exists() and not _has_sample_marker(map_path):
        raise VaultError("示例地图路径已被其他内容占用")
    if image_path.exists() and not map_path.exists() and image_path.read_bytes() != map_bytes:
        raise VaultError("示例地图图片路径已被其他内容占用")

    (world_root / "pages").mkdir(parents=True, exist_ok=True)
    (world_root / "assets").mkdir(exist_ok=True)
    map_root.mkdir(exist_ok=True)
    if not world_file.exists():
        Vault._atomic_text(
            world_file,
            yaml.safe_dump(
                {
                    "id": SAMPLE_WORLD_ID,
                    "name": SAMPLE_WORLD_NAME,
                    "default_branch": "main",
                    "sample_set": SAMPLE_SET,
                    "created_at": SAMPLE_CREATED_AT,
                },
                allow_unicode=True,
                sort_keys=False,
            ),
        )

    for item in SAMPLE_ENTRIES:
        path = _entry_path(vault, item)
        Vault._atomic_text(path, dump_markdown(item["metadata"], item["body"]))

    Vault._atomic_text(
        template_path,
        yaml.safe_dump(SAMPLE_TEMPLATE, allow_unicode=True, sort_keys=False, width=100),
    )

    Vault._atomic_bytes(image_path, map_bytes)
    Vault._atomic_text(
        map_path,
        yaml.safe_dump(SAMPLE_MAP, allow_unicode=True, sort_keys=False, width=100),
    )
    return sample_status(vault)


def delete_sample(vault: Vault) -> dict[str, Any]:
    removed_entries = 0
    for item in SAMPLE_ENTRIES:
        path = _entry_path(vault, item)
        if not path.is_file():
            continue
        document = vault.read_path(path)
        if document.metadata.get("sample_set") != SAMPLE_SET:
            continue
        path.unlink()
        removed_entries += 1
        history = vault.root / ".history" / "entries" / str(item["metadata"]["id"])
        if history.is_dir() and not history.is_symlink():
            shutil.rmtree(history)

    template_path = vault.root / "templates" / f"{SAMPLE_TEMPLATE_ID}.yaml"
    if _has_sample_marker(template_path):
        template_path.unlink()
        versions = vault.root / "templates" / "versions" / SAMPLE_TEMPLATE_ID
        if versions.is_dir() and not versions.is_symlink():
            shutil.rmtree(versions)

    map_root = vault.root / "worlds" / SAMPLE_WORLD_ID / "maps"
    map_path = map_root / f"{SAMPLE_MAP_ID}.yaml"
    if _has_sample_marker(map_path):
        map_path.unlink()
        (map_root / SAMPLE_MAP_FILENAME).unlink(missing_ok=True)

    world_root = vault.root / "worlds" / SAMPLE_WORLD_ID
    remaining_files = (
        [path for path in world_root.rglob("*") if path.is_file() and path.name != "world.yaml"]
        if world_root.is_dir()
        else []
    )
    if world_root.is_dir() and not remaining_files:
        shutil.rmtree(world_root)
    return {**sample_status(vault), "removed_entries": removed_entries}


def _has_sample_marker(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    return isinstance(value, dict) and value.get("sample_set") == SAMPLE_SET


def _entry_path(vault: Vault, item: dict[str, Any]) -> Path:
    metadata = item["metadata"]
    return (
        vault.root
        / "worlds"
        / SAMPLE_WORLD_ID
        / "pages"
        / str(metadata["type"])
        / f"{metadata['id']}.md"
    )
