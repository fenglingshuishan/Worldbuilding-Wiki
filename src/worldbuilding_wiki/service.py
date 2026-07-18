from __future__ import annotations

import difflib
import json
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from worldbuilding_wiki.ai import AIClient
from worldbuilding_wiki.errors import ValidationError, VaultError
from worldbuilding_wiki.index import VaultIndex, index_path
from worldbuilding_wiki.paths import AppPaths, ConfigStore
from worldbuilding_wiki.rendering import render_markdown
from worldbuilding_wiki.resources import sample_data_dir
from worldbuilding_wiki.sample import (
    delete_sample as delete_sample_content,
)
from worldbuilding_wiki.sample import (
    restore_sample as restore_sample_content,
)
from worldbuilding_wiki.sample import (
    sample_status as get_sample_status,
)
from worldbuilding_wiki.store import ENTRY_STATUSES, Vault, dump_markdown, safe_slug, utc_local_now
from worldbuilding_wiki.transfer import TransferManager


class WorldbuildingService:
    def __init__(self, paths: AppPaths, initial_vault: Path | None = None):
        self.paths = paths
        self.paths.ensure()
        self.config = ConfigStore(paths)
        self.transfer = TransferManager(paths.imports, paths.exports)
        self.ai = AIClient()
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

    def create_vault(
        self,
        name: str,
        world_name: str,
        path: Path | None = None,
        *,
        include_sample: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            target = path or self.paths.default_vaults / safe_slug(name, "vault")
            vault = Vault.create(target, name, world_name)
            try:
                if include_sample:
                    restore_sample_content(vault, sample_data_dir() / "tidal-archive-map.webp")
            except Exception:
                shutil.rmtree(vault.root, ignore_errors=True)
                raise
            self._activate(vault)
            return self.info()

    def create_world(self, name: str) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            world = vault.create_world(name)
            index.rebuild(vault)
            return world

    def sample_status(self) -> dict[str, Any]:
        vault, _ = self.require()
        return get_sample_status(vault)

    def restore_sample(self) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            result = restore_sample_content(vault, sample_data_dir() / "tidal-archive-map.webp")
            index.rebuild(vault)
            return result

    def delete_sample(self) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            result = delete_sample_content(vault)
            index.rebuild(vault)
            return result

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

    def entry_history(self, entry_id: str) -> dict[str, Any]:
        vault, _ = self.require()
        return vault.list_entry_history(entry_id)

    def entry_diff(
        self, entry_id: str, revision_id: str, against_revision_id: str | None = None
    ) -> dict[str, Any]:
        vault, _ = self.require()
        history = vault.list_entry_history(entry_id)
        base = vault.read_entry_revision(entry_id, revision_id)
        summaries = {
            item["revision_id"]: item for item in [history["current"], *history["revisions"]]
        }
        if against_revision_id:
            target = vault.read_entry_revision(entry_id, against_revision_id)
            target_id = against_revision_id
        else:
            target = vault.find_entry(entry_id)
            target_id = "current"
        base_text = dump_markdown(base.metadata, base.body)
        target_text = dump_markdown(target.metadata, target.body)
        raw_lines = list(
            difflib.unified_diff(
                base_text.splitlines(),
                target_text.splitlines(),
                fromfile=revision_id,
                tofile=target_id,
                lineterm="",
            )
        )
        lines = []
        added = 0
        deleted = 0
        for line in raw_lines:
            if line.startswith(("--- ", "+++ ", "@@ ")):
                kind = "header"
            elif line.startswith("+"):
                kind = "add"
                added += 1
            elif line.startswith("-"):
                kind = "delete"
                deleted += 1
            else:
                kind = "context"
            lines.append({"kind": kind, "text": line})
        return {
            "entry_id": entry_id,
            "base": summaries[revision_id],
            "target": summaries[target_id],
            "summary": {"added": added, "deleted": deleted},
            "lines": lines,
        }

    def restore_entry(
        self, entry_id: str, revision_id: str, expected_hash: str | None
    ) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            vault.restore_entry(entry_id, revision_id, expected_hash)
            index.rebuild(vault)
            return self.get_entry(entry_id)

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
            if "custom_fields" in payload:
                current = vault.find_entry(entry_id)
                template_ref = payload.get("template", current.metadata.get("template"))
                if not isinstance(template_ref, dict):
                    raise ValidationError("没有模板的条目不能写入自定义字段")
                template = vault.find_template_version(
                    str(template_ref.get("id", "")), int(template_ref.get("version", 0))
                )
                payload["custom_fields"] = vault._normalize_custom_fields(
                    template, payload["custom_fields"]
                )
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

    def list_branches(self) -> list[str]:
        vault, _ = self.require()
        return sorted({str(item.metadata.get("branch", "main")) for item in vault.iter_entries()})

    def create_branch_variant(self, entry_id: str, target_branch: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", target_branch):
            raise ValidationError("分支名必须以小写字母开头，只包含小写字母、数字和连字符")
        with self._lock:
            vault, index = self.require()
            source = vault.find_entry(entry_id)
            if source.metadata.get("branch", "main") == target_branch:
                raise ValidationError("目标分支不能与来源分支相同")
            lineage = str(source.metadata.get("variant_of") or source.metadata["id"])
            if any(
                item.metadata.get("branch", "main") == target_branch
                and str(item.metadata.get("variant_of") or item.metadata["id"]) == lineage
                for item in vault.iter_entries()
            ):
                raise ValidationError("目标分支已经存在该条目的变体")
            payload = {
                key: source.metadata[key] for key in ("type", "title", "status", "world", "branch")
            }
            payload.update(
                {
                    "branch": target_branch,
                    "aliases": source.metadata.get("aliases", []),
                    "tags": source.metadata.get("tags", []),
                    "relations": source.metadata.get("relations", []),
                    "time": source.metadata.get("time"),
                    "claims": source.metadata.get("claims"),
                    "body": source.body,
                    "variant_of": lineage,
                }
            )
            if source.metadata.get("template"):
                payload.update(
                    {
                        "template_id": source.metadata["template"]["id"],
                        "template_version": source.metadata["template"]["version"],
                        "custom_fields": source.metadata.get("custom_fields", {}),
                    }
                )
            document = vault.create_entry(payload)
            index.rebuild(vault)
            return self.get_entry(str(document.metadata["id"]))

    def compare_branches(self, base_branch: str, target_branch: str) -> dict[str, Any]:
        if base_branch == target_branch:
            raise ValidationError("比较分支不能相同")
        vault, _ = self.require()
        documents = [
            item for item in vault.iter_entries() if item.metadata["status"] != "deprecated"
        ]
        base = {
            str(item.metadata.get("variant_of") or item.metadata["id"]): item
            for item in documents
            if item.metadata.get("branch", "main") == base_branch
        }
        target_groups: dict[str, list[Any]] = {}
        for item in documents:
            if item.metadata.get("branch", "main") == target_branch:
                lineage = str(item.metadata.get("variant_of") or item.metadata["id"])
                target_groups.setdefault(lineage, []).append(item)
        changes = []
        conflicts = []
        for lineage, variants in target_groups.items():
            if len(variants) > 1:
                conflicts.append(
                    {"lineage": lineage, "entry_ids": [item.metadata["id"] for item in variants]}
                )
                continue
            target = variants[0]
            base_item = base.get(lineage)
            kind = "added"
            if base_item:
                kind = (
                    "synchronized"
                    if self._branch_content(base_item) == self._branch_content(target)
                    else "overridden"
                )
            changes.append(
                {
                    "kind": kind,
                    "lineage": lineage,
                    "target_id": target.metadata["id"],
                    "target_title": target.metadata["title"],
                    "base_id": base_item.metadata["id"] if base_item else None,
                    "base_title": base_item.metadata["title"] if base_item else None,
                }
            )
        inherited = [
            {"id": item.metadata["id"], "title": item.metadata["title"], "lineage": lineage}
            for lineage, item in base.items()
            if lineage not in target_groups
        ]
        return {
            "base_branch": base_branch,
            "target_branch": target_branch,
            "changes": changes,
            "inherited": inherited,
            "conflicts": conflicts,
            "summary": {
                "added": sum(item["kind"] == "added" for item in changes),
                "overridden": sum(item["kind"] == "overridden" for item in changes),
                "synchronized": sum(item["kind"] == "synchronized" for item in changes),
                "inherited": len(inherited),
                "conflicts": len(conflicts),
            },
        }

    def merge_branches(
        self, base_branch: str, target_branch: str, decisions: dict[str, str]
    ) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            comparison = self.compare_branches(base_branch, target_branch)
            actionable = {
                item["target_id"]: item
                for item in comparison["changes"]
                if item["kind"] in {"added", "overridden"}
            }
            unknown = set(decisions) - set(actionable)
            if unknown:
                raise ValidationError("合并决定包含不属于本次比较的条目")
            documents = {
                entry_id: vault.find_entry(entry_id)
                for entry_id in set(decisions)
                | {
                    str(item["base_id"])
                    for item in actionable.values()
                    if item["base_id"] and item["target_id"] in decisions
                }
            }
            snapshots = {item.path: item.path.read_bytes() for item in documents.values()}
            created_paths = []
            records = []
            try:
                for target_id, action in decisions.items():
                    if action not in {"accept_target", "keep_base", "copy_as_draft"}:
                        raise ValidationError(f"不支持的合并动作：{action}")
                    change = actionable[target_id]
                    target = documents[target_id]
                    if action == "keep_base":
                        records.append({"target_id": target_id, "action": action})
                        continue
                    if action == "copy_as_draft":
                        copy = vault.create_entry(
                            {
                                "type": target.metadata["type"],
                                "title": f"{target.metadata['title']}（来自 {target_branch}）",
                                "status": "draft",
                                "world": target.metadata["world"],
                                "branch": base_branch,
                                "tags": target.metadata.get("tags", []),
                                "relations": target.metadata.get("relations", []),
                                "time": target.metadata.get("time"),
                                "body": target.body,
                            }
                        )
                        created_paths.append(copy.path)
                        records.append(
                            {
                                "target_id": target_id,
                                "action": action,
                                "created_id": copy.metadata["id"],
                            }
                        )
                        continue
                    if change["kind"] == "added":
                        vault.update_entry(
                            target_id,
                            {
                                "branch": base_branch,
                                "merge_record": {
                                    "source_branch": target_branch,
                                    "source_id": target_id,
                                    "merged_at": utc_local_now(),
                                },
                            },
                            target.hash,
                        )
                        records.append({"target_id": target_id, "action": action})
                        continue
                    base = documents[str(change["base_id"])]
                    payload = self._branch_content(target)
                    payload["merge_record"] = {
                        "source_branch": target_branch,
                        "source_id": target_id,
                        "merged_at": utc_local_now(),
                    }
                    vault.update_entry(str(base.metadata["id"]), payload, base.hash)
                    records.append(
                        {"target_id": target_id, "base_id": base.metadata["id"], "action": action}
                    )
                index.rebuild(vault)
            except Exception:
                for path, data in snapshots.items():
                    Vault._atomic_bytes(path, data)
                for path in created_paths:
                    path.unlink(missing_ok=True)
                index.rebuild(vault)
                raise
            return {"merged": len(records), "records": records}

    @staticmethod
    def _branch_content(document: Any) -> dict[str, Any]:
        keys = (
            "title",
            "aliases",
            "status",
            "tags",
            "relations",
            "time",
            "claims",
            "template",
            "custom_fields",
        )
        return {key: document.metadata[key] for key in keys if key in document.metadata} | {
            "body": document.body
        }

    def graph(self, entry_id: str) -> dict[str, Any]:
        _, index = self.require()
        return index.graph(entry_id)

    def graph_overview(self, limit: int = 250) -> dict[str, Any]:
        _, index = self.require()
        return index.graph_overview(limit)

    def list_templates(self) -> list[dict[str, Any]]:
        vault, _ = self.require()
        return vault.list_templates()

    def get_template_version(self, template_id: str, version: int) -> dict[str, Any]:
        vault, _ = self.require()
        return vault.find_template_version(template_id, version)

    def create_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            vault, _ = self.require()
            return vault.create_template(payload)

    def update_template(self, template_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            vault, _ = self.require()
            return vault.update_template(template_id, payload)

    def delete_template(self, template_id: str) -> dict[str, Any]:
        with self._lock:
            vault, _ = self.require()
            vault.delete_template(template_id)
            return {"deleted": template_id}

    def preview_template_migration(
        self, entry_ids: list[str], target_template_id: str, field_mapping: dict[str, str]
    ) -> dict[str, Any]:
        vault, _ = self.require()
        unique_ids = list(dict.fromkeys(entry_ids))
        if not unique_ids or len(unique_ids) > 200:
            raise ValidationError("模板迁移需选择 1 至 200 个条目")
        target = vault.find_template(target_template_id)
        reverse_mapping = {target_id: source_id for source_id, target_id in field_mapping.items()}
        entries = []
        can_apply = True
        for entry_id in unique_ids:
            document = vault.find_entry(entry_id)
            source_values = document.metadata.get("custom_fields", {})
            candidate = {}
            for field in target["fields"]:
                source_id = reverse_mapping.get(field["id"], field["id"])
                if source_id in source_values:
                    candidate[field["id"]] = source_values[source_id]
            warnings = []
            try:
                normalized = vault._normalize_custom_fields(target, candidate)
            except ValidationError as exc:
                normalized = candidate
                warnings.append(str(exc))
                can_apply = False
            entries.append(
                {
                    "id": entry_id,
                    "title": document.metadata["title"],
                    "source_template": document.metadata.get("template"),
                    "target_template": {"id": target["id"], "version": target["version"]},
                    "custom_fields": normalized,
                    "warnings": warnings,
                }
            )
        return {
            "target": target,
            "field_mapping": field_mapping,
            "entries": entries,
            "can_apply": can_apply,
        }

    def migrate_template_entries(
        self, entry_ids: list[str], target_template_id: str, field_mapping: dict[str, str]
    ) -> dict[str, Any]:
        with self._lock:
            vault, index = self.require()
            preview = self.preview_template_migration(entry_ids, target_template_id, field_mapping)
            if not preview["can_apply"]:
                messages = [warning for item in preview["entries"] for warning in item["warnings"]]
                raise ValidationError("；".join(dict.fromkeys(messages)))
            documents = [vault.find_entry(item["id"]) for item in preview["entries"]]
            snapshots = {document.path: document.path.read_bytes() for document in documents}
            try:
                for document, item in zip(documents, preview["entries"], strict=True):
                    vault.update_entry(
                        str(document.metadata["id"]),
                        {
                            "template": item["target_template"],
                            "custom_fields": item["custom_fields"],
                        },
                        document.hash,
                    )
                index.rebuild(vault)
            except Exception:
                for path, data in snapshots.items():
                    Vault._atomic_bytes(path, data)
                index.rebuild(vault)
                raise
            return {
                "migrated": len(documents),
                "entry_ids": [str(document.metadata["id"]) for document in documents],
                "target_template": preview["entries"][0]["target_template"],
            }

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

    def list_maps(self, world: str = "") -> list[dict[str, Any]]:
        vault, _ = self.require()
        return [self._map_for_web(item) for item in vault.list_maps(world)]

    def create_map(self, world: str, name: str, filename: str, data: bytes) -> dict[str, Any]:
        with self._lock:
            vault, _ = self.require()
            return self._map_for_web(vault.create_map(world, name, filename, data))

    def update_map(
        self, map_id: str, payload: dict[str, Any], expected_hash: str | None
    ) -> dict[str, Any]:
        with self._lock:
            vault, _ = self.require()
            current = vault.read_map(map_id)
            for marker in payload.get("markers", current["markers"]):
                location = vault.find_entry(str(marker.get("location_id", "")))
                if location.metadata["type"] != "location":
                    raise ValidationError("地图标记只能引用地点条目")
                if location.metadata["world"] != current["world"]:
                    raise ValidationError("地图标记与地点必须属于同一个世界")
            return self._map_for_web(vault.update_map(map_id, payload, expected_hash))

    def delete_map(self, map_id: str, expected_hash: str | None) -> dict[str, str]:
        with self._lock:
            vault, _ = self.require()
            vault.delete_map(map_id, expected_hash)
            return {"deleted": map_id}

    @staticmethod
    def _map_for_web(value: dict[str, Any]) -> dict[str, Any]:
        return {
            **value,
            "image_url": "/api/vault-assets/" + quote(str(value["image"]), safe="/"),
        }

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

    def ai_info(self) -> dict[str, Any]:
        return self.ai.settings.public_info()

    def preview_ai_scope(self, entry_ids: list[str], instruction: str) -> dict[str, Any]:
        vault, _ = self.require()
        unique_ids = list(dict.fromkeys(entry_ids))
        if not unique_ids or len(unique_ids) > 20:
            raise ValidationError("AI 建议需选择 1 至 20 个条目")
        request_text = instruction.strip()
        if not request_text or len(request_text) > 2000:
            raise ValidationError("建议目标不能为空，且最多 2000 字")
        documents = [vault.find_entry(entry_id) for entry_id in unique_ids]
        parts = [f"任务：{request_text}", "以下是用户明确选择发送的条目："]
        scope = []
        for document in documents:
            metadata = document.metadata
            parts.append(
                f"\n## {metadata['title']} ({metadata['id']})\n"
                f"类型：{metadata['type']}；状态：{metadata['status']}；分支：{metadata.get('branch', 'main')}\n"
                f"标签：{', '.join(metadata.get('tags', []))}\n\n{document.body}"
            )
            scope.append(
                {
                    "id": metadata["id"],
                    "title": metadata["title"],
                    "content_hash": document.hash,
                    "body_characters": len(document.body),
                    "fields": ["id", "title", "type", "status", "branch", "tags", "body"],
                }
            )
        prompt = "\n".join(parts)
        if len(prompt) > 60000:
            raise ValidationError("所选 AI 上下文超过 60000 字，请减少条目")
        return {
            "provider": self.ai_info(),
            "instruction": request_text,
            "scope": scope,
            "prompt_characters": len(prompt),
            "prompt": prompt,
        }

    def generate_ai_proposal(self, entry_ids: list[str], instruction: str) -> dict[str, Any]:
        preview = self.preview_ai_scope(entry_ids, instruction)
        content = self.ai.generate(preview["prompt"])
        proposal = {
            "id": f"proposal-{uuid.uuid4().hex[:12]}",
            "created_at": utc_local_now(),
            "instruction": preview["instruction"],
            "provider": preview["provider"],
            "scope": preview["scope"],
            "content": content,
            "status": "proposal",
        }
        target = self.paths.runtime / "proposals" / f"{proposal['id']}.json"
        Vault._atomic_text(target, json.dumps(proposal, ensure_ascii=False, indent=2) + "\n")
        return proposal

    def list_ai_proposals(self) -> list[dict[str, Any]]:
        root = self.paths.runtime / "proposals"
        result = []
        for path in sorted(root.glob("proposal-*.json"), reverse=True):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                result.append(value)
        return result

    def delete_ai_proposal(self, proposal_id: str) -> dict[str, str]:
        if not re.fullmatch(r"proposal-[0-9a-f]{12}", proposal_id):
            raise ValidationError("提案 ID 不合法")
        target = (self.paths.runtime / "proposals" / f"{proposal_id}.json").resolve()
        root = (self.paths.runtime / "proposals").resolve()
        if target.parent != root or not target.is_file():
            raise VaultError("AI 提案不存在")
        target.unlink()
        return {"deleted": proposal_id}
