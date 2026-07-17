from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

from worldbuilding_wiki.errors import VaultError
from worldbuilding_wiki.index import VaultIndex, index_path
from worldbuilding_wiki.paths import AppPaths, ConfigStore
from worldbuilding_wiki.rendering import render_markdown
from worldbuilding_wiki.store import ENTRY_STATUSES, Vault, safe_slug
from worldbuilding_wiki.transfer import TransferManager


class WorldbuildingService:
    def __init__(self, paths: AppPaths, initial_vault: Path | None = None):
        self.paths = paths
        self.paths.ensure()
        self.config = ConfigStore(paths)
        self.transfer = TransferManager(paths.imports, paths.exports)
        self._lock = threading.RLock()
        self.vault: Vault | None = None
        self.index: VaultIndex | None = None
        candidate = initial_vault
        if candidate is None:
            configured = self.config.read().get("active_vault")
            candidate = Path(configured) if configured else None
        if candidate:
            try:
                self.open_vault(candidate)
            except VaultError:
                self.config.clear_active_vault()

    def info(self) -> dict[str, Any]:
        config = self.config.read()
        if not self.vault:
            return {
                "ready": False,
                "active_vault": None,
                "recent_vaults": config["recent_vaults"],
                "default_vaults_path": str(self.paths.default_vaults),
            }
        return {
            "ready": True,
            "active_vault": str(self.vault.root),
            "vault": self.vault.metadata,
            "worlds": self.vault.worlds(),
            "recent_vaults": config["recent_vaults"],
            "default_vaults_path": str(self.paths.default_vaults),
        }

    def create_vault(self, name: str, world_name: str, path: Path | None = None) -> dict[str, Any]:
        with self._lock:
            target = path or self.paths.default_vaults / safe_slug(name, "vault")
            vault = Vault.create(target, name, world_name)
            self._activate(vault)
            return self.info()

    def create_world(self, name: str) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            world = vault.create_world(name)
            index.rebuild(vault)
            return world

    def open_vault(self, path: Path) -> dict[str, Any]:
        with self._lock:
            vault = Vault(path)
            self._activate(vault)
            return self.info()

    def close_vault(self) -> dict[str, Any]:
        with self._lock:
            self.vault = None
            self.index = None
            self.config.clear_active_vault()
            return self.info()

    def delete_vault(self, confirmation: str) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            name = str(vault.metadata.get("name", ""))
            if confirmation != name:
                raise VaultError("确认名称与当前世界库名称不一致，未执行删除")

            root = vault.root.resolve()
            protected = {
                Path(root.anchor).resolve(),
                Path.home().resolve(),
                self.paths.root.resolve(),
                self.paths.runtime.resolve(),
                self.paths.default_vaults.resolve(),
            }
            if root in protected:
                raise VaultError(f"拒绝删除受保护目录：{root}")

            database = index.database
            try:
                shutil.rmtree(root)
            except OSError as exc:
                raise VaultError(f"无法删除世界库目录：{exc}") from exc

            self.vault = None
            self.index = None
            self.config.forget_vault(root)
            try:
                database.unlink(missing_ok=True)
            except OSError as exc:
                raise VaultError(f"世界库已删除，但无法清理索引：{exc}") from exc

            return {**self.info(), "deleted_vault": str(root)}

    def _activate(self, vault: Vault) -> None:
        self.vault = vault
        self.index = VaultIndex(index_path(self.paths.runtime, vault.root))
        self.index.rebuild(vault)
        self.config.set_active_vault(vault.root)

    def require(self) -> tuple[Vault, VaultIndex]:
        if not self.vault or not self.index:
            raise VaultError("尚未打开世界库")
        return self.vault, self.index

    def reindex(self) -> dict[str, int]:
        with self._lock:
            vault, index = self.require()
            return index.rebuild(vault)

    def list_entries(self, **filters: Any) -> list[dict[str, Any]]:
        _, index = self.require()
        return index.list_entries(**filters)

    def dashboard(self) -> dict[str, Any]:
        _, index = self.require()
        return index.dashboard()

    def get_entry(self, entry_id: str) -> dict[str, Any]:
        vault, index = self.require()
        document = vault.find_entry(entry_id)
        context = index.entry_context(entry_id)
        lookup = self._reference_lookup()

        def resolve(target: str) -> tuple[str, str] | None:
            result = lookup.get(target.casefold())
            if not result:
                return None
            return f"#/entry/{result['id']}", result["title"]

        rendered_body = self._rewrite_asset_urls(document.body, document.path, vault.root)
        return {
            "entry": document.as_dict(),
            "rendered_html": render_markdown(rendered_body, resolve),
            **context,
        }

    def create_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            document = vault.create_entry(payload)
            index.rebuild(vault)
            return self.get_entry(str(document.metadata["id"]))

    def update_entry(
        self, entry_id: str, payload: dict[str, Any], expected_hash: str | None
    ) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            vault.update_entry(entry_id, payload, expected_hash)
            index.rebuild(vault)
            return self.get_entry(entry_id)

    def archive_entry(self, entry_id: str, expected_hash: str | None) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            vault.archive_entry(entry_id, expected_hash)
            index.rebuild(vault)
            return self.get_entry(entry_id)

    def checks(self) -> list[dict[str, Any]]:
        _, index = self.require()
        return index.list_checks()

    def timeline(self) -> list[dict[str, Any]]:
        _, index = self.require()
        return index.timeline()

    def graph(self, entry_id: str) -> dict[str, Any]:
        _, index = self.require()
        return index.graph(entry_id)

    def graph_overview(self, limit: int = 250) -> dict[str, Any]:
        _, index = self.require()
        return index.graph_overview(limit)

    def list_templates(self) -> list[dict[str, Any]]:
        vault, _ = self.require()
        return vault.list_templates()

    def create_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            vault, _ = self.require()
            return vault.create_template(payload)

    def delete_template(self, template_id: str) -> dict[str, Any]:
        with self._lock:
            vault, _ = self.require()
            vault.delete_template(template_id)
            return {"deleted": template_id}

    def bulk_update_entries(
        self,
        entry_ids: list[str],
        *,
        status: str | None = None,
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(entry_ids))
        if not unique_ids:
            raise VaultError("至少选择一个条目")
        if len(unique_ids) > 200:
            raise VaultError("单次最多批量处理 200 个条目")
        if status is not None and status not in ENTRY_STATUSES:
            raise VaultError(f"不支持的内容状态：{status}")
        if status is None and not add_tags and not remove_tags:
            raise VaultError("批量操作至少需要调整状态或标签")
        with self._lock:
            vault, index = self.require()
            documents = [vault.find_entry(entry_id) for entry_id in unique_ids]
            snapshots = {document.path: document.path.read_bytes() for document in documents}
            added = [str(item).strip() for item in (add_tags or []) if str(item).strip()]
            removed = {str(item).strip() for item in (remove_tags or []) if str(item).strip()}
            try:
                for document in documents:
                    payload: dict[str, Any] = {}
                    if status is not None:
                        payload["status"] = status
                    if added or removed:
                        tags = [
                            tag for tag in document.metadata.get("tags", []) if tag not in removed
                        ]
                        payload["tags"] = list(dict.fromkeys([*tags, *added]))
                    vault.update_entry(str(document.metadata["id"]), payload, document.hash)
                index.rebuild(vault)
            except Exception:
                for path, data in snapshots.items():
                    Vault._atomic_bytes(path, data)
                index.rebuild(vault)
                raise
            return {"updated": len(unique_ids), "entry_ids": unique_ids}

    def save_asset(self, world: str, filename: str, data: bytes) -> dict[str, Any]:
        with self._lock:
            vault, _ = self.require()
            return vault.save_asset(world, filename, data)

    def read_asset(self, relative_path: str) -> tuple[Path, bytes]:
        vault, _ = self.require()
        return vault.read_asset(relative_path)

    def export_worldvault(self, scope: str, world_ids: list[str]) -> Path:
        vault, _ = self.require()
        return self.transfer.export_worldvault(vault, scope=scope, world_ids=world_ids)

    def export_review(self) -> Path:
        vault, _ = self.require()
        return self.transfer.export_review(vault)

    def preview_import(
        self,
        archive_bytes: bytes,
        *,
        mode: str,
        new_vault_name: str = "导入的世界库",
        target_path: str | None = None,
    ) -> dict[str, Any]:
        if mode == "merge":
            vault, _ = self.require()
            target = vault.root
        elif target_path:
            target = Path(target_path)
        else:
            target = self.paths.default_vaults / safe_slug(new_vault_name, "imported-vault")
            if target.exists():
                counter = 2
                candidate = target.with_name(f"{target.name}-{counter}")
                while candidate.exists():
                    counter += 1
                    candidate = target.with_name(f"{target.name}-{counter}")
                target = candidate
        return self.transfer.preview_import(archive_bytes, target_path=target, mode=mode)

    def commit_import(self, token: str, conflict_choices: dict[str, str]) -> dict[str, Any]:
        with self._lock:
            result = self.transfer.commit_import(token, conflict_choices=conflict_choices)
            self.open_vault(Path(result["target_path"]))
            return {**result, "info": self.info(), "index": self.reindex()}

    def _reference_lookup(self) -> dict[str, dict[str, str]]:
        entries = self.list_entries(limit=1000)
        result: dict[str, dict[str, str]] = {}
        for entry in entries:
            value = {"id": entry["id"], "title": entry["title"]}
            result[entry["id"].casefold()] = value
            result[entry["title"].casefold()] = value
            for alias in entry["aliases"]:
                result.setdefault(alias.casefold(), value)
        return result

    @staticmethod
    def _rewrite_asset_urls(body: str, document_path: Path, vault_root: Path) -> str:
        pattern = re.compile(r"(!?\[[^\]]*\]\()([^\s)]+)(\))")

        def replace(match: re.Match[str]) -> str:
            target = match.group(2)
            if target.startswith(("http://", "https://", "/", "#", "mailto:")):
                return match.group(0)
            resolved = (document_path.parent / target).resolve()
            try:
                relative = resolved.relative_to(vault_root.resolve())
            except ValueError:
                return match.group(0)
            if (
                len(relative.parts) < 4
                or relative.parts[0] != "worlds"
                or relative.parts[2]
                not in {
                    "assets",
                    "maps",
                }
            ):
                return match.group(0)
            url = "/api/vault-assets/" + quote(relative.as_posix(), safe="/")
            return f"{match.group(1)}{url}{match.group(3)}"

        return pattern.sub(replace, body)

    def diagnostics(self) -> dict[str, Any]:
        vault, index = self.require()
        return {
            "vault": str(vault.root),
            "index": str(index.database),
            "config": str(self.paths.config_file),
            "metadata": json.loads(json.dumps(vault.metadata, ensure_ascii=False, default=str)),
        }
