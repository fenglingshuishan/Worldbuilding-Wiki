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

`main` 是默认正史；其他分支继承基准分支内容，只保存覆盖项和新增项。每个变体文件有自己的唯一条目 ID，并通过 `variant_of` 保持跨分支谱系，避免同一世界库出现重复 ID。

当前文件模型用 `variant_of` 指向基准条目的稳定 ID 来表达跨分支谱系，变体自身仍有唯一文件 ID。比较结果区分继承、新增、覆盖、已同步和重复谱系冲突；合并记录写入 `merge_record`，采用目标前进入条目历史。

## 8. 附件与地图

图片、音频、PDF 和地图原图保存在 `assets/` 或 `maps/` 中，Markdown 使用相对路径引用。索引只保存元数据和缩略图缓存。地图标记用同目录独立 YAML 描述，不修改原图，也不把坐标写死在数据库里。

```yaml
id: map_0123456789ab
name: 北境总图
world: aurora
image: worlds/aurora/maps/map_0123456789ab.webp
layers:
  - id: base
    name: 默认图层
    visible: true
  - id: politics
    name: 政治边界
    visible: true
markers:
  - id: marker-abc123
    layer_id: politics
    location_id: loc_01JEXAMPLE
    x: 0.25
    y: 0.75
```

坐标相对原图宽高归一化为 `0..1`；标记必须引用同一世界的地点条目和现有图层。每张地图包含 1—50 个图层、最多 1000 个标记。地图元数据使用内容哈希进行乐观锁保护。

## 9. 数据校验

写入前检查：

- ID 唯一且格式合法；
- 条目类型、状态和分支存在；
- 关系两端存在，且类型组合被允许；
- 标题和别名不会造成无法消解的链接；
- 时间范围的最早值不晚于最晚值；
- 相对资源路径不能逃出 `vault/`。

校验失败时保留编辑草稿并展示原因，不写入半成品文件。

### 9.1 条目历史

应用内每次改写条目前，Vault 将旧 Markdown 原文保存为：

```text
.history/entries/<entry-id>/<UTC-timestamp>-<sha256>.md
```

版本文件不可变，文件名不包含 Windows 非法字符。列表只接受合法条目 ID、合法版本 ID、世界库内部常规文件和与目录条目 ID 一致的 front matter；符号链接、损坏文件和错配版本不会参与恢复。每条保留最近 100 个快照。

恢复时必须提交页面读取到的当前内容哈希。Vault 先快照当前文件，再恢复目标版本的可编辑字段，同时保留当前条目的稳定 ID、类型、世界和创建时间，并刷新更新时间。这样恢复本身也可撤回。

## 10. 内置示例数据

应用包保存一份只读的虚构示例标准副本。用户在首次新建世界库时选择载入后，它才会作为普通 Markdown、YAML 和 WebP 文件写入世界库。示例世界、条目和地图使用固定 ID，并用以下字段标识所属集合：

```yaml
sample_set: tidal-archive-v1
tags:
  - 示例全套数据
```

删除流程同时校验固定路径、稳定 ID 和 `sample_set`，不按世界名称、标题或标签模糊删除。若示例世界中仍有用户文件，则保留世界目录；还原只覆盖带同一标记的标准示例，遇到非示例 ID 冲突时中止。示例一旦写入世界库，便属于当前可编辑内容，会进入完整 `.worldvault`；应用内的只读标准副本不单独导出。

## 11. 世界传输包

`.worldvault` 是使用标准 ZIP 容器的开放传输格式，扩展名用于让应用直接识别。它不是程序安装包，也不包含索引数据库、缓存、日志、密钥、绝对路径、Git 元数据或隐藏的本地条目历史。它迁移当前可编辑内容；完整历史需通过整个世界库目录的文件级备份保留。

```text
aurora-2026-07-16.worldvault
├── manifest.json
├── checksums.sha256
└── content/
    ├── vault.yaml
    ├── worlds/
    └── templates/
```

`manifest.json` 至少记录：

```json
{
  "format": "worldbuilding-vault",
  "format_version": 1,
  "exported_by": "worldbuilding-wiki",
  "app_version": "0.4.0",
  "exported_at": "2026-07-16T18:00:00+08:00",
  "scope": "world",
  "root_ids": ["aurora"],
  "file_count": 128,
  "content_bytes": 9437184
}
```

`checksums.sha256` 覆盖 `content/` 下每个文件。清单的格式版本独立于应用版本：新应用必须读取仍在支持期内的旧格式；遇到更高版本时只能预览并拒绝写入，不能猜测解析。

### 11.1 导出范围

- `vault`：完整世界库；
- `world`：一个或多个完整世界；
- `selection`：选定条目，以及用户确认包含的链接目标、关系端点、模板、历法和附件依赖。

正史、草稿、传闻、废弃设定和分支都属于内容。导出界面必须按状态汇总数量并允许排除；排除内容导致断链时给出警告。

### 11.2 冲突判定

导入合并依据稳定 ID 和内容哈希，而非标题：

| 情况 | 默认动作 |
| --- | --- |
| ID 不存在 | 新增 |
| ID 与哈希均相同 | 跳过 |
| ID 相同但哈希不同 | 标记冲突，等待选择 |
| 标题相同但 ID 不同 | 保留两者，提示可能重复 |
| 引用目标不在包内和目标库内 | 报告缺失依赖 |

冲突选择包括保留本地、采用导入版本、另存为草稿副本或逐字段/正文比较。批量选择前展示影响数量；“替换整个世界库”必须先生成恢复快照。

### 11.3 导入安全

导入器拒绝绝对路径、`..` 路径、符号链接、超出配置上限的文件数量/展开体积、校验和不符、大小写规范化后重复的路径、Windows 保留名称、损坏的 Markdown 条目和重复条目 ID。所有内容先展开到临时暂存区，完成 schema、引用与安全校验后再原子移动到目标世界库。
