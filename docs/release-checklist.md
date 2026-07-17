# 发布检查表

- 版本：0.2.0
- 状态：本地候选已验证；`main` 与标签构建由 GitHub Actions 复验
- 日期：2026-07-17
- 发行对象：Python wheel/sdist、Linux x64 与 Windows x64 独立程序

## 1. 通用门禁

- [x] Ruff 静态检查与格式检查通过。
- [x] 20 项自动化测试通过。
- [x] Python 与 JavaScript 语法检查通过。
- [x] 工作区文档规范检查无错误或警告。
- [x] wheel 和 sdist 内容检查通过，包含完整前端资源。
- [x] wheel 在全新 `/tmp` 虚拟环境安装，版本为 `0.2.0`。
- [x] 已安装 wheel 在源码目录外启动真实服务，健康、世界库创建和驾驶舱接口通过。
- [x] 世界库 schema 与 `.worldvault` 格式版本保持兼容。

## 2. Linux x64 候选

- [x] PyInstaller 目录式程序构建成功。
- [x] 发行 `tar.gz` 结构、许可证、说明和变更日志检查通过。
- [x] 解压后的真实程序在源码和虚拟环境之外执行 `--version`。
- [x] 解压后的真实程序启动回环服务，创建匿名世界库并读取驾驶舱。
- [x] 发行包不包含世界库、密钥、索引、日志和 Git 元数据。
- [x] 生成独立 SHA-256 文件。

Linux 本地候选位于被 Git 忽略的构建目录和 `/tmp`，不提交仓库。

## 3. 远程与 Windows 门禁

`main` 推送后必须先等待 `Build release artifacts` 完整成功，再创建 `v0.2.0` 标签。标签工作流必须满足：

- Ubuntu 重新执行测试、构建 wheel/sdist，并在全新环境启动 wheel 服务。
- Windows 与 Ubuntu 原生 runner 分别执行测试、PyInstaller 构建和独立程序真实接口验证。
- Release 聚合作业只在全部生产作业成功后运行。
- Release 包含 wheel、sdist、Windows ZIP、Linux tar.gz、平台独立校验文件与统一 `SHA256SUMS`。
- 标签、Release 和 `main` 中的发布提交一致；Release 不是草稿或预发布。

不得用 Linux 结果推断 Windows 可用。Windows 资产只由 Windows runner 生成，Linux 资产只由 Ubuntu runner 生成。

## 4. 数据与回滚

发布验证只使用匿名临时世界库，不读取真实用户内容。若分支 CI 失败，不创建标签；若标签工作流在 Release 创建前失败，先修复流水线并发布修正版，不覆盖已公开资产。程序升级问题可使用旧程序目录重新打开外部世界库，任何情况下都禁止用 SQLite 索引覆盖 Markdown 真源。

0.1.1 的历史发布证据保留在 Git 标签 `v0.1.1` 及仓库历史中。
