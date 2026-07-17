from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from worldbuilding_wiki import __version__
from worldbuilding_wiki.errors import WorldbuildingWikiError
from worldbuilding_wiki.paths import AppPaths, platform_data_dir
from worldbuilding_wiki.service import WorldbuildingService
from worldbuilding_wiki.web import create_app


def _configure_utf8(stream: object) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if not reconfigure:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="worldbuilding-wiki", description="本地世界观知识库")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--data-dir", type=Path, help="配置、索引和临时文件目录")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="启动本机应用")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=3764)
    serve.add_argument("--vault", type=Path)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--log-level", default="warning")

    create = subparsers.add_parser("create-vault", help="创建一个空世界库")
    create.add_argument("path", type=Path)
    create.add_argument("--name", default="我的世界库")
    create.add_argument("--world", default="主世界")

    reindex = subparsers.add_parser("reindex", help="重建当前或指定世界库索引")
    reindex.add_argument("--vault", type=Path)

    export = subparsers.add_parser("export", help="导出当前世界库")
    export.add_argument("--vault", type=Path)
    export.add_argument("--review", action="store_true", help="导出静态 HTML 审阅包")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_utf8(sys.stdout)
    _configure_utf8(sys.stderr)
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "serve"
    root = (args.data_dir or platform_data_dir()).expanduser().resolve()
    paths = AppPaths(root)
    try:
        if command == "create-vault":
            service = WorldbuildingService(paths)
            info = service.create_vault(args.name, args.world, args.path)
            print(info["active_vault"])
            return 0
        if command == "reindex":
            service = WorldbuildingService(paths, args.vault)
            print(service.reindex())
            return 0
        if command == "export":
            service = WorldbuildingService(paths, args.vault)
            path = (
                service.export_review() if args.review else service.export_worldvault("vault", [])
            )
            print(path)
            return 0
        return run_server(
            paths=paths,
            vault=getattr(args, "vault", None),
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 3764),
            open_browser=not getattr(args, "no_browser", False),
            log_level=getattr(args, "log_level", "warning"),
        )
    except WorldbuildingWikiError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


def run_server(
    *,
    paths: AppPaths,
    vault: Path | None,
    host: str,
    port: int,
    open_browser: bool,
    log_level: str,
) -> int:
    service = WorldbuildingService(paths, vault)
    app = create_app(service)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(128)
    actual_port = int(sock.getsockname()[1])
    url = f"http://{host}:{actual_port}/"
    print(f"Worldbuilding Wiki {__version__} 正在运行：{url}")
    print("请在应用内选择“退出”，或在此终端按 Ctrl+C 停止服务。")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    config = uvicorn.Config(app, host=host, port=actual_port, log_level=log_level)
    server = uvicorn.Server(config)
    app.state.shutdown_callback = lambda: setattr(server, "should_exit", True)
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    return 0
