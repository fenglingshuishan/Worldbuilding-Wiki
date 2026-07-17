Worldbuilding Wiki
==================

这是一个本地优先的个人世界观知识库。

快速开始
--------

Windows：双击 WorldbuildingWiki.exe。
Linux：在终端运行 ./WorldbuildingWiki。

程序启动后会打开本机浏览器。第一次运行请选择：

1. 新建世界库；
2. 打开包含 vault.yaml 的现有世界库；
3. 导入 .worldvault 世界传输包。

你的世界观数据不会保存在本程序目录中。替换或删除程序前，仍建议在应用的
“迁移与发布”页面导出 .worldvault 传输包。

安全边界
--------

- 服务默认只监听 127.0.0.1，不向局域网或公网开放。
- .worldvault 包含世界观内容，不包含 API 密钥、索引和运行日志。
- 静态审阅包只能浏览，不应作为可恢复编辑数据的唯一备份。

停止程序
--------

关闭浏览器标签页不会停止程序。请在“平台设置”中选择“退出本地程序”；Linux
也可以在启动终端按 Ctrl+C。

命令行
------

WorldbuildingWiki --version
WorldbuildingWiki serve --no-browser --port 3764
WorldbuildingWiki create-vault PATH --name "我的世界库" --world "主世界"
WorldbuildingWiki reindex --vault PATH
WorldbuildingWiki export --vault PATH

本发行包不附带任何具体世界观数据。
