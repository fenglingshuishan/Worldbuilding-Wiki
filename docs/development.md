# 开发与验证

- 适用版本：0.4.0
- 受众：项目维护者
- 工作目录：项目仓库根目录

## 1. 环境

需要 Python 3.11 或更高版本。新环境固定放在项目内：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

运行应用：

```bash
.venv/bin/worldbuilding-wiki --data-dir /tmp/worldwiki-dev serve --no-browser --port 3764
```

健康检查应返回 `status: ok`：

```bash
curl --noproxy '*' -fsS http://127.0.0.1:3764/api/health
```

## 2. 质量门禁

```bash
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/pytest
.venv/bin/python -m compileall -q src scripts
```

测试覆盖 Markdown 往返、乐观锁、中文检索、链接与关系、时间线、一致性检查、危险 Markdown、传输包无损迁移、冲突策略、路径穿越、跨平台路径碰撞、损坏/重复条目、篡改检测、静态审阅和 HTTP API。

## 3. Python 发行包

```bash
rm -rf build dist
.venv/bin/python -m build
.venv/bin/python /home/hcj/.codex/skills/package-python-webapp/scripts/inspect_distributions.py dist/*
```

必须在新虚拟环境、源码目录之外安装 wheel，并验证 CLI 和真实接口。不能使用 editable install 作为发行证明。

## 4. 独立程序

```bash
.venv/bin/python scripts/build_release.py
```

脚本执行 PyInstaller 目录式构建，复制用户说明、许可证和变更日志，生成平台压缩包与 SHA-256，然后执行 `scripts/verify_release.py`。Linux 产物不能改名作为 Windows 产物；Windows 版本必须在 Windows 原生构建环境生成。

应用资源通过 Python package resources 定位，必须同时适用于源码、wheel 和冻结目录。若 `index.html`、CSS 或 JavaScript 缺失，应用应直接报错，不能启动残缺界面。

## 5. API 与统一入口

源码运行、console script、`python -m worldbuilding_wiki` 和冻结程序都调用 `worldbuilding_wiki.cli:main`。主要接口：

| 路径 | 用途 |
| --- | --- |
| `GET /api/health` | 版本和运行状态 |
| `POST /api/vaults` | 创建世界库 |
| `DELETE /api/vaults/current` | 输入当前世界库名称后永久删除正文与索引 |
| `POST /api/worlds` | 创建世界 |
| `GET /api/dashboard` | 首页聚合指标、分布与最近活动 |
| `GET /api/sample` | 查询内置示例是否完整、部分存在或未载入 |
| `POST /api/sample/restore` | 原位写入或重置固定标记的标准示例 |
| `DELETE /api/sample` | 仅删除带固定示例标记的数据 |
| `/api/entries` | 条目检索和写入 |
| `POST /api/entries/bulk` | 最多 200 条的状态与标签批量治理 |
| `/api/templates` | 查询、创建、升级和删除世界库自定义模板 |
| `/api/templates/migration/*` | 预览并原子应用跨模板字段迁移 |
| `GET /api/graph` | 全库语义关系与 Wiki 提及网络 |
| `/api/maps` | 地图原图、图层和地点标记 |
| `/api/branches/*` | 创建变体、比较分支和执行显式合并决定 |
| `/api/ai/*` | 预览发送范围并管理只读 AI 提案 |
| `POST /api/assets` | 上传附件 |
| `GET /api/checks` | 一致性报告 |
| `GET /api/timeline` | 时间线 |
| `/api/export/*` | 世界包和审阅包 |
| `/api/import/*` | 预览与提交导入 |

开发环境可在 `/api/docs` 查看 OpenAPI 页面。

## 6. 失败处理

- wheel 缺静态文件：检查 `tool.setuptools.package-data` 和构建产物成员。
- 冻结程序缺模块：检查 PyInstaller 警告和动态导入；当前 spec 收集 Uvicorn 子模块。
- 程序只能在源码目录运行：说明资源定位错误，必须在 `/tmp` 等目录重新验证。
- 导入测试失败：不得跳过校验；检查清单、内容哈希、暂存和回滚路径。
- 端口无法绑定：选择空闲回环端口；不要为绕过冲突改为监听公网地址。
- Windows 产物未验证：保持发布门禁未完成，不用 Linux 结果推断 Windows 可用。

## 7. 数据与安全影响

自动化测试只使用临时虚构数据。发行目录扫描拒绝 `vault`、`.worldvault`、SQLite、日志、环境文件和 Git 元数据。构建或测试脚本不得读取真实用户世界库作为夹具。
