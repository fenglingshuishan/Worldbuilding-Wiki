# 数据模型

## 1. 两层模型

系统将内容分为两个层次：

- **正文层**：Markdown 文件和资源附件，是唯一不可丢失的真源。
- **索引层**：SQLite 中的全文索引、反向链接、规范化关系和检查结果，可随时重建。

应用写入正文后再更新索引；如果索引更新失败，正文仍然有效，并在下一次启动时重新扫描。

## 2. 建议的内容目录

```text
vault/
├── vault.yaml
├── worlds/
│   └── aurora/
│       ├── world.yaml
│       ├── pages/
│       │   ├── character/
│       │   ├── location/
│       │   ├── organization/
│       │   ├── event/
│       │   ├── culture/
│       │   ├── rule/
│       │   └── concept/
│       ├── maps/
│       └── assets/
└── templates/
```

文件名使用稳定 ID 或 `ID-短标题.md`，链接显示名与文件名解耦。修改标题不会破坏关系；应用仍兼容手写的 `[[标题]]`，保存时解析到 ID。

## 3. 条目格式

```markdown
---
id: char_01JEXAMPLE
type: character
title: 林烬
aliases:
  - 北境信使
world: aurora
branch: main
status: canon
tags:
  - 信使
  - 北境
created_at: 2026-07-16T10:00:00+08:00
updated_at: 2026-07-16T10:00:00+08:00
---

# 林烬

林烬出生于 [[loc_01JEXAMPLE|雾港]]，目前效忠于
[[org_01JEXAMPLE|北境邮驿会]]。
```

必填字段只有 `id`、`type`、`title` 和 `status`。时间戳由应用维护。人类可读正文不应重复存储所有结构化关系。

## 4. 关系模型

关系是一等数据，核心字段为：

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定关系 ID |
| `subject` | 主体条目 ID |
| `predicate` | 关系类型，如 `member_of` |
| `object` | 客体条目 ID 或受控字面量 |
| `valid_from` | 生效时间，可为空或模糊 |
| `valid_to` | 失效时间，可为空或模糊 |
| `branch` | 所属时间分支 |
| `status` | 正史、草稿、传闻或废弃 |
| `source` | 支持该关系的条目或声明 |
| `note` | 限定条件和解释 |

首批受控关系包括 `located_in`、`born_in`、`member_of`、`leads`、`parent_of`、`ally_of`、`enemy_of`、`participates_in`、`causes`、`precedes` 和 `uses`。关系类型声明自身是否对称、是否有反向名称、允许哪些主体/客体类型。

关系可写在独立 YAML 文件中，也可由条目元数据和 Wiki 链接导出。MVP 采用条目旁的结构化 `relations` 字段作为写入格式，SQLite 统一规范化读取；正文中的普通链接只表示“提及”，不自动推断强语义。

## 5. 时间模型

世界内历法不能直接作为排序依据。每个时间点先映射到世界自己的连续序号 `ordinal`，再由历法格式化显示。

```yaml
time:
  calendar: imperial
  display: 星历 312 年霜月下旬
  earliest_ordinal: 113880
  latest_ordinal: 113889
  precision: ten_day
```

这种范围模型可表达“约某年”“某月下旬”和史料互相矛盾的日期。没有足够信息时保留显示文本，不伪造精确序号。不同世界之间默认不可比较时间。

事件包含起止范围；人物出生、死亡和任职期使用相同模型。一致性规则只能在时间范围确定不会重叠时报告硬冲突，其余情况标为待确认。

## 6. 说法与事实

世界内观点用声明表达：

```yaml
claims:
  - id: claim_01JEXAMPLE
    speaker: org_01JEXAMPLE
    statement: 王都大火由旧王党策划
    about: event_01JEXAMPLE
    source: source_01JEXAMPLE
    reliability: disputed
```

`reliability` 是作者的整理标签，不是系统计算出的真相。声明与正史事实分别检索和展示，避免“某角色认为”被误读为“世界确实如此”。

## 7. 分支时间线

`branch` 形成父子结构。`main` 是默认正史；子分支继承父分支内容，只保存覆盖项和新增项。条目 ID 在分支间保持一致，便于比较差异。系统禁止形成循环继承。

## 8. 附件与地图

图片、音频、PDF 和地图原图保存在 `assets/` 或 `maps/` 中，Markdown 使用相对路径引用。索引只保存元数据和缩略图缓存。地图标记用独立 YAML/JSON 描述，不修改原图，也不把坐标写死在数据库里。

## 9. 数据校验

写入前检查：

- ID 唯一且格式合法；
- 条目类型、状态和分支存在；
- 关系两端存在，且类型组合被允许；
- 标题和别名不会造成无法消解的链接；
- 时间范围的最早值不晚于最晚值；
- 相对资源路径不能逃出 `vault/`。

校验失败时保留编辑草稿并展示原因，不写入半成品文件。
