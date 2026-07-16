# Worldbuilding Wiki

面向个人创作者的本地优先世界观知识库。当前版本 `0.1.1` 已可运行：支持多世界、结构化条目、Markdown/Wiki 链接、附件、搜索、关系、时间线、一致性检查、`.worldvault` 导入导出和静态 HTML 审阅包。

程序默认仅监听 `127.0.0.1`。世界观正文保存在用户选择的世界库中，SQLite 只保存可删除重建的索引；程序发行包不附带任何具体世界观数据。

## 快速使用

普通用户应下载与操作系统匹配的独立发行压缩包，解压后运行 `WorldbuildingWiki.exe`（Windows）或 `WorldbuildingWiki`（Linux）。不需要安装 Python、Node.js 或数据库。

源码开发方式（工作目录为本仓库）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/worldbuilding-wiki
```

程序会打开本机浏览器。首次运行可新建世界库、打开已有 `vault.yaml`，或导入 `.worldvault`。关闭浏览器不会停止后端；请在“设置”中选择“退出本地程序”。

## 已实现能力

- 人物、地点、组织、事件、群体、文化、规则、物件、概念和来源条目。
- 正史、草稿、传闻和废弃状态；别名、标签和时间线分支。
- `[[条目标题]]`、`[[条目 ID|显示名]]`、反向链接与局部关系。
- 多世界、模糊时间范围、语义关系和关系目标校验。
- 中文标题、别名、正文和标签搜索。
- 图片、地图、PDF、音频和文本附件；单文件上限 50 MiB。
- 断链、重复别名、孤立条目、废弃引用、事件顺序和地点重叠检查。
- 带格式版本和 SHA-256 的 `.worldvault`；安全预检、冲突选择、暂存、恢复快照和失败回滚。
- 无需安装应用即可浏览的静态 HTML 审阅包。
- wheel/sdist、Linux 独立目录程序，以及 Windows/Linux 原生构建流水线。

## 文档

- [用户指南](docs/user-guide.md)
- [开发与验证](docs/development.md)
- [发布检查表](docs/release-checklist.md)
- [产品设计](docs/product-design.md)
- [数据模型](docs/data-model.md)
- [技术架构](docs/architecture.md)
- [分发与数据迁移](docs/portability.md)
- [实施路线与验收场景](docs/mvp-plan.md)
- [架构决策](docs/decisions/)

## 项目目录

```text
src/worldbuilding_wiki/  应用、领域逻辑和内置前端
tests/                   存储、索引、迁移、安全和 API 测试
scripts/                 构建与发行验证脚本
packaging/               发行包内用户说明
docs/                    产品、架构、使用和维护文档
runtime/                 仓库内占位；实际运行状态不提交 Git
```

## 数据边界

- 世界库：Markdown、YAML、地图和附件，是用户长期数据。
- 运行目录：SQLite 索引、导入暂存、临时导出和恢复快照。
- 应用目录：只读程序、依赖、前端和内置说明。
- 密钥：当前版本未启用外部 AI，也不会写入世界传输包。

不支持多台设备同时写入同一个网络共享目录。跨设备编辑请显式导出、复制并导入 `.worldvault`，或在应用关闭后使用用户自行管理的 Git 工作流。
