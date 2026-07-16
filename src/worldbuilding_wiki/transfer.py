from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from worldbuilding_wiki import __version__
from worldbuilding_wiki.errors import TransferError
from worldbuilding_wiki.rendering import render_markdown
from worldbuilding_wiki.store import (
    Vault,
    content_hash,
    dump_markdown,
    parse_markdown,
    utc_local_now,
)

MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILE_COUNT = 20_000
MAX_COMPRESSION_RATIO = 200


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TransferManager:
    def __init__(self, imports_root: Path, exports_root: Path):
        self.imports_root = imports_root
        self.exports_root = exports_root
        self.backups_root = imports_root.parent / "backups"
        self.imports_root.mkdir(parents=True, exist_ok=True)
        self.exports_root.mkdir(parents=True, exist_ok=True)
        self.backups_root.mkdir(parents=True, exist_ok=True)

    def export_worldvault(
        self, vault: Vault, *, scope: str = "vault", world_ids: list[str] | None = None
    ) -> Path:
        if scope not in {"vault", "world"}:
            raise TransferError("当前版本只支持导出整个世界库或完整世界")
        available_worlds = {item["id"] for item in vault.worlds()}
        selected = set(world_ids or [])
        if scope == "world":
            if not selected:
                raise TransferError("导出单个世界时必须选择 world_ids")
            unknown = selected - available_worlds
            if unknown:
                raise TransferError("世界不存在：" + ", ".join(sorted(unknown)))
        else:
            selected = available_worlds

        files = self._vault_files(vault, scope, selected)
        timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        target = (
            self.exports_root
            / f"{self._safe_filename(vault.metadata.get('name', 'vault'))}-{timestamp}.worldvault"
        )
        temporary = target.with_suffix(".tmp")
        checksums: list[tuple[str, str]] = []
        total_size = 0
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path, relative in files:
                    data = path.read_bytes()
                    archive.writestr(f"content/{relative.as_posix()}", data)
                    checksums.append((content_hash(data), relative.as_posix()))
                    total_size += len(data)
                checksum_text = "".join(f"{digest}  {name}\n" for digest, name in checksums)
                manifest = {
                    "format": "worldbuilding-vault",
                    "format_version": 1,
                    "exported_by": "worldbuilding-wiki",
                    "app_version": __version__,
                    "exported_at": utc_local_now(),
                    "scope": scope,
                    "root_ids": sorted(selected),
                    "file_count": len(files),
                    "content_bytes": total_size,
                }
                archive.writestr(
                    "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
                )
                archive.writestr("checksums.sha256", checksum_text)
            self._validate_archive(temporary, extract_to=None)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def export_review(self, vault: Vault) -> Path:
        timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        target = (
            self.exports_root
            / f"{self._safe_filename(vault.metadata.get('name', 'vault'))}-review-{timestamp}.zip"
        )
        temporary = target.with_suffix(".tmp")
        documents = list(vault.iter_entries())
        reference_map: dict[str, tuple[str, str]] = {}
        for doc in documents:
            entry_id = str(doc.metadata["id"])
            title = str(doc.metadata["title"])
            reference_map[entry_id.casefold()] = (entry_id, title)
            reference_map[title.casefold()] = (entry_id, title)
            for alias in doc.metadata.get("aliases", []):
                reference_map.setdefault(str(alias).casefold(), (entry_id, title))

        page_paths = {
            str(doc.metadata["id"]): Path(doc.path.relative_to(vault.root)).with_suffix(".html")
            for doc in documents
        }
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                cards = []
                for doc in documents:
                    entry_id = str(doc.metadata["id"])
                    output_path = page_paths[entry_id]

                    def resolve(
                        target_ref: str, current: Path = output_path
                    ) -> tuple[str, str] | None:
                        item = reference_map.get(target_ref.casefold())
                        if not item:
                            return None
                        target_id, title = item
                        relative_url = os.path.relpath(
                            page_paths[target_id], current.parent
                        ).replace(os.sep, "/")
                        return relative_url, title

                    body_html = render_markdown(doc.body, resolve)
                    title = self._escape(str(doc.metadata["title"]))
                    metadata = doc.metadata
                    page = self._review_page(
                        title=title,
                        subtitle=f"{metadata['type']} · {metadata['status']} · {metadata.get('world', '')}",
                        body=body_html,
                        home=os.path.relpath(Path("index.html"), output_path.parent).replace(
                            os.sep, "/"
                        ),
                    )
                    archive.writestr(output_path.as_posix(), page)
                    cards.append(
                        {
                            "title": str(metadata["title"]),
                            "type": str(metadata["type"]),
                            "status": str(metadata["status"]),
                            "path": output_path.as_posix(),
                        }
                    )
                for path in vault.root.rglob("*"):
                    if not path.is_file() or path.suffix.lower() in {".md", ".yaml", ".yml"}:
                        continue
                    relative = path.relative_to(vault.root)
                    if any(part.startswith(".") for part in relative.parts):
                        continue
                    archive.write(path, relative.as_posix())
                archive.writestr("index.html", self._review_index(vault, cards))
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def preview_import(
        self,
        archive_bytes: bytes,
        *,
        target_path: Path,
        mode: str,
    ) -> dict[str, Any]:
        if len(archive_bytes) > MAX_ARCHIVE_BYTES:
            raise TransferError("传输包超过 512 MiB 上限")
        if mode not in {"new", "merge"}:
            raise TransferError("导入模式必须是 new 或 merge")
        token = uuid.uuid4().hex
        stage = self.imports_root / token
        stage.mkdir(parents=True)
        archive_path = stage / "incoming.worldvault"
        archive_path.write_bytes(archive_bytes)
        content_root = stage / "content"
        try:
            manifest = self._validate_archive(archive_path, extract_to=content_root)
            incoming = Vault(content_root)
            incoming_entries = {doc.metadata["id"]: doc for doc in incoming.iter_entries()}
            target_path = target_path.expanduser().resolve()
            target_entries: dict[str, Any] = {}
            if mode == "new":
                if target_path.exists() and any(target_path.iterdir()):
                    raise TransferError(f"新建导入目录不是空目录：{target_path}")
            else:
                target = Vault(target_path)
                target_entries = {doc.metadata["id"]: doc for doc in target.iter_entries()}

            additions = []
            identical = []
            conflicts = []
            for entry_id, incoming_doc in incoming_entries.items():
                local = target_entries.get(entry_id)
                if not local:
                    additions.append(self._entry_label(incoming_doc))
                elif local.hash == incoming_doc.hash:
                    identical.append(self._entry_label(incoming_doc))
                else:
                    conflicts.append(
                        {
                            **self._entry_label(incoming_doc),
                            "local_hash": local.hash,
                            "incoming_hash": incoming_doc.hash,
                            "local_updated_at": local.metadata.get("updated_at"),
                            "incoming_updated_at": incoming_doc.metadata.get("updated_at"),
                        }
                    )
            file_conflicts = []
            if mode == "merge":
                incoming_entry_paths = {
                    doc.path.relative_to(incoming.root) for doc in incoming_entries.values()
                }
                for incoming_file in sorted(content_root.rglob("*")):
                    if not incoming_file.is_file():
                        continue
                    relative = incoming_file.relative_to(content_root)
                    if relative in incoming_entry_paths or relative == Path("vault.yaml"):
                        continue
                    local_file = target_path / relative
                    if local_file.is_file() and sha256_file(local_file) != sha256_file(
                        incoming_file
                    ):
                        file_conflicts.append(
                            {
                                "path": relative.as_posix(),
                                "local_hash": sha256_file(local_file),
                                "incoming_hash": sha256_file(incoming_file),
                                "bytes": incoming_file.stat().st_size,
                            }
                        )
            state = {
                "token": token,
                "target_path": str(target_path),
                "mode": mode,
                "manifest": manifest,
                "created_at": utc_local_now(),
            }
            (stage / "state.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            return {
                **state,
                "additions": additions,
                "identical": identical,
                "conflicts": conflicts,
                "file_conflicts": file_conflicts,
                "incoming_entries": len(incoming_entries),
            }
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def commit_import(
        self,
        token: str,
        *,
        conflict_choices: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        stage = (self.imports_root / token).resolve()
        try:
            stage.relative_to(self.imports_root.resolve())
        except ValueError as exc:
            raise TransferError("非法导入令牌") from exc
        state_path = stage / "state.json"
        if not state_path.is_file():
            raise TransferError("导入预览已失效，请重新选择传输包")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        source = stage / "content"
        target_path = Path(state["target_path"])
        choices = conflict_choices or {}
        if state["mode"] == "new":
            result = self._commit_new(source, target_path)
        else:
            result = self._commit_merge(source, target_path, choices)
        shutil.rmtree(stage, ignore_errors=True)
        return {**result, "target_path": str(target_path), "token": token}

    def _commit_new(self, source: Path, target: Path) -> dict[str, int]:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and any(target.iterdir()):
            raise TransferError(f"目标目录在预览后变为非空：{target}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.import-", dir=target.parent))
        try:
            shutil.copytree(source, temporary, dirs_exist_ok=True)
            Vault(temporary)
            if target.exists():
                target.rmdir()
            os.replace(temporary, target)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
        return {"added": sum(1 for _ in Vault(target).iter_entries()), "updated": 0, "skipped": 0}

    def _commit_merge(
        self, source: Path, target_path: Path, choices: dict[str, str]
    ) -> dict[str, Any]:
        incoming = Vault(source)
        target = Vault(target_path)
        snapshot = self.export_worldvault(target, scope="vault")
        backup_name = (
            f"before-import-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-%f')}.worldvault"
        )
        backup_path = self.backups_root / backup_name
        os.replace(snapshot, backup_path)
        incoming_entries = {doc.metadata["id"]: doc for doc in incoming.iter_entries()}
        local_entries = {doc.metadata["id"]: doc for doc in target.iter_entries()}
        rollback = Path(tempfile.mkdtemp(prefix="worldwiki-rollback-", dir=target.root.parent))
        created: list[Path] = []
        changed: list[tuple[Path, Path]] = []
        added = updated = skipped = 0
        try:
            for entry_id, incoming_doc in incoming_entries.items():
                local = local_entries.get(entry_id)
                relative = incoming_doc.path.relative_to(incoming.root)
                destination = target.root / relative
                if local and local.hash == incoming_doc.hash:
                    skipped += 1
                    continue
                if local:
                    destination = local.path
                    choice = choices.get(str(entry_id), "local")
                    if choice == "local":
                        skipped += 1
                        continue
                    if choice == "draft":
                        metadata, body = parse_markdown(
                            incoming_doc.path.read_text(encoding="utf-8")
                        )
                        metadata["id"] = self._new_id_like(str(metadata["id"]))
                        metadata["status"] = "draft"
                        metadata["title"] = f"{metadata['title']}（导入副本）"
                        metadata["updated_at"] = utc_local_now()
                        destination = destination.with_name(f"{metadata['id']}.md")
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text(dump_markdown(metadata, body), encoding="utf-8")
                        created.append(destination)
                        added += 1
                        continue
                    if choice != "incoming":
                        raise TransferError(f"未知冲突选择：{choice}")
                    backup = rollback / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, backup)
                    changed.append((destination, backup))
                    shutil.copy2(incoming_doc.path, destination)
                    updated += 1
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(incoming_doc.path, destination)
                    created.append(destination)
                    added += 1

            for source_file in source.rglob("*"):
                if not source_file.is_file() or source_file.suffix.lower() == ".md":
                    continue
                relative = source_file.relative_to(source)
                if relative == Path("vault.yaml"):
                    continue
                destination = target.root / relative
                if destination.exists():
                    if sha256_file(destination) == sha256_file(source_file):
                        continue
                    choice = choices.get(f"file:{relative.as_posix()}", "local")
                    if choice == "local":
                        continue
                    if choice != "incoming":
                        raise TransferError(f"未知文件冲突选择：{choice}")
                    backup = rollback / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, backup)
                    changed.append((destination, backup))
                    shutil.copy2(source_file, destination)
                    updated += 1
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, destination)
                created.append(destination)
            Vault(target.root)
        except Exception:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            for destination, backup in reversed(changed):
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, destination)
            raise
        finally:
            shutil.rmtree(rollback, ignore_errors=True)
        return {
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "recovery_snapshot": str(backup_path),
        }

    def _validate_archive(self, archive_path: Path, extract_to: Path | None) -> dict[str, Any]:
        if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise TransferError("传输包超过大小上限")
        try:
            archive = zipfile.ZipFile(archive_path)
        except zipfile.BadZipFile as exc:
            raise TransferError("文件不是有效的 `.worldvault` ZIP 容器") from exc
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILE_COUNT + 2:
                raise TransferError("传输包文件数量超过上限")
            names: set[str] = set()
            expanded = 0
            for info in infos:
                normalized = self._safe_archive_name(info.filename)
                if normalized in names:
                    raise TransferError(f"传输包包含重复路径：{normalized}")
                names.add(normalized)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise TransferError(f"传输包不允许符号链接：{normalized}")
                expanded += info.file_size
                if expanded > MAX_EXPANDED_BYTES:
                    raise TransferError("传输包展开体积超过上限")
                if (
                    info.compress_size
                    and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
                ):
                    raise TransferError(f"文件压缩比异常：{normalized}")
            required = {"manifest.json", "checksums.sha256", "content/vault.yaml"}
            missing = required - names
            if missing:
                raise TransferError("传输包缺少：" + ", ".join(sorted(missing)))
            try:
                manifest = json.loads(archive.read("manifest.json"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise TransferError("manifest.json 无法解析") from exc
            if (
                manifest.get("format") != "worldbuilding-vault"
                or manifest.get("format_version") != 1
            ):
                raise TransferError("不支持的世界传输包格式或版本")
            checksum_map = self._parse_checksums(archive.read("checksums.sha256"))
            content_names = sorted(
                name[len("content/") :]
                for name in names
                if name.startswith("content/") and not name.endswith("/")
            )
            if set(content_names) != set(checksum_map):
                raise TransferError("校验和清单与 content 文件列表不一致")
            for relative in content_names:
                actual = hashlib.sha256(archive.read(f"content/{relative}")).hexdigest()
                if actual != checksum_map[relative]:
                    raise TransferError(f"文件校验和不匹配：{relative}")
            if manifest.get("file_count") != len(content_names):
                raise TransferError("manifest 的文件数量不正确")
            if manifest.get("content_bytes") != sum(
                archive.getinfo(f"content/{name}").file_size for name in content_names
            ):
                raise TransferError("manifest 的内容大小不正确")
            if extract_to is not None:
                extract_to.mkdir(parents=True, exist_ok=True)
                for relative in content_names:
                    destination = extract_to / PurePosixPath(relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(f"content/{relative}"))
        return manifest

    @staticmethod
    def _parse_checksums(data: bytes) -> dict[str, str]:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransferError("checksums.sha256 不是 UTF-8") from exc
        result = {}
        for line in text.splitlines():
            if not line:
                continue
            parts = line.split("  ", 1)
            if len(parts) != 2 or len(parts[0]) != 64:
                raise TransferError("checksums.sha256 格式错误")
            name = TransferManager._safe_archive_name(parts[1])
            if name in result:
                raise TransferError(f"校验和路径重复：{name}")
            result[name] = parts[0]
        return result

    @staticmethod
    def _safe_archive_name(name: str) -> str:
        if "\\" in name:
            raise TransferError(f"传输包路径包含反斜杠：{name}")
        path = PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts or "." in path.parts:
            raise TransferError(f"传输包路径不安全：{name}")
        normalized = path.as_posix()
        if normalized.startswith("/"):
            raise TransferError(f"传输包路径不安全：{name}")
        return normalized

    @staticmethod
    def _vault_files(vault: Vault, scope: str, selected: set[str]) -> list[tuple[Path, Path]]:
        result: list[tuple[Path, Path]] = []
        for path in sorted(vault.root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(vault.root)
            if any(part.startswith(".") for part in relative.parts):
                continue
            if scope == "world" and relative.parts[0] == "worlds":
                if len(relative.parts) < 2 or relative.parts[1] not in selected:
                    continue
            result.append((path, relative))
        return result

    @staticmethod
    def _entry_label(document: Any) -> dict[str, str]:
        return {
            "id": str(document.metadata["id"]),
            "title": str(document.metadata["title"]),
            "type": str(document.metadata["type"]),
            "status": str(document.metadata["status"]),
        }

    @staticmethod
    def _new_id_like(entry_id: str) -> str:
        prefix = entry_id.split("_", 1)[0]
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _safe_filename(value: Any) -> str:
        text = "".join(char if char.isalnum() or char in "-_" else "-" for char in str(value))
        return text.strip("-") or "world-vault"

    @staticmethod
    def _escape(value: str) -> str:
        import html

        return html.escape(value, quote=True)

    def _review_index(self, vault: Vault, cards: list[dict[str, str]]) -> str:
        card_html = "".join(
            '<a class="card" data-search="{search}" href="{path}"><strong>{title}</strong>'
            "<span>{type} · {status}</span></a>".format(
                search=self._escape(f"{item['title']} {item['type']} {item['status']}".casefold()),
                path=self._escape(item["path"]),
                title=self._escape(item["title"]),
                type=self._escape(item["type"]),
                status=self._escape(item["status"]),
            )
            for item in cards
        )
        title = self._escape(str(vault.metadata.get("name", "世界观审阅")))
        return f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title} · 只读审阅</title><style>{self._review_css()}</style>
<main><header><p class="eyebrow">只读世界观快照 · {self._escape(utc_local_now())}</p>
<h1>{title}</h1><input id="q" placeholder="筛选条目"></header>
<section id="cards" class="grid">{card_html}</section></main>
<script>const q=document.querySelector('#q');q.addEventListener('input',()=>{{const v=q.value.toLowerCase();
document.querySelectorAll('.card').forEach(x=>x.hidden=!x.dataset.search.includes(v));}});</script></html>"""

    def _review_page(self, *, title: str, subtitle: str, body: str, home: str) -> str:
        return f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title}</title><style>{self._review_css()}</style><main>
<a href="{self._escape(home)}">← 返回索引</a><header><p class="eyebrow">{self._escape(subtitle)}</p>
<h1>{title}</h1></header><article>{body}</article></main></html>"""

    @staticmethod
    def _review_css() -> str:
        return """
:root{font-family:ui-serif,'Noto Serif SC',serif;color:#27231f;background:#f3efe6}
body{margin:0}main{max-width:980px;margin:auto;padding:48px 24px}header{margin:24px 0 40px}
h1{font-size:clamp(2rem,6vw,4.5rem);line-height:1.05;margin:.2em 0}a{color:#76512d}
.eyebrow{font-family:ui-sans-serif,sans-serif;letter-spacing:.08em;color:#7a7268}
input{width:min(100%,420px);padding:12px;border:1px solid #c9bda9;background:#fffaf0;border-radius:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.card{display:flex;flex-direction:column;gap:8px;padding:18px;background:#fffaf0;border:1px solid #d9cfbf;
border-radius:10px;text-decoration:none}.card span{font:12px ui-sans-serif;color:#766d62}article{font-size:18px;line-height:1.8}
blockquote{border-left:3px solid #9c7955;padding-left:16px;color:#5f554b}code{background:#e8e0d3;padding:.15em .35em}
img{max-width:100%}table{border-collapse:collapse}td,th{border:1px solid #c9bda9;padding:8px}
"""
