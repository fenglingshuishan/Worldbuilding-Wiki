from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from worldbuilding_wiki.errors import ConflictError, ValidationError, VaultError

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)(.*)\Z", re.DOTALL)
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")
VALID_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
VALID_ID_RE = re.compile(r"^[a-z][a-z0-9]*_[0-9a-f]{12}$")

ENTRY_TYPES = {
    "character",
    "location",
    "organization",
    "event",
    "group",
    "culture",
    "rule",
    "artifact",
    "concept",
    "source",
}
ENTRY_STATUSES = {"canon", "draft", "rumor", "deprecated"}
ALLOWED_ASSET_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".pdf",
    ".mp3",
    ".ogg",
    ".wav",
    ".txt",
    ".csv",
}
MAX_ASSET_BYTES = 50 * 1024 * 1024


def utc_local_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_markdown(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValidationError("Markdown 缺少合法的 YAML front matter")
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"YAML 元数据无法解析：{exc}") from exc
    if not isinstance(metadata, dict):
        raise ValidationError("YAML 元数据必须是对象")
    return metadata, match.group(2).lstrip("\r\n")


def dump_markdown(metadata: dict[str, Any], body: str) -> str:
    frontmatter = yaml.safe_dump(
        metadata,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    ).rstrip()
    normalized_body = body.rstrip() + "\n" if body.strip() else ""
    return f"---\n{frontmatter}\n---\n\n{normalized_body}"


def extract_wiki_links(body: str) -> list[dict[str, str]]:
    return [
        {"target": match.group(1).strip(), "label": (match.group(2) or "").strip()}
        for match in WIKI_LINK_RE.finditer(body)
    ]


def make_id(entry_type: str) -> str:
    prefix = {
        "character": "char",
        "location": "loc",
        "organization": "org",
        "event": "event",
        "group": "group",
        "culture": "culture",
        "rule": "rule",
        "artifact": "artifact",
        "concept": "concept",
        "source": "source",
    }[entry_type]
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def safe_slug(value: str, fallback: str = "world") -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug or not VALID_NAME_RE.fullmatch(slug):
        slug = f"{fallback}-{uuid.uuid4().hex[:8]}"
    return slug


@dataclass(slots=True)
class EntryDocument:
    metadata: dict[str, Any]
    body: str
    path: Path
    hash: str

    def as_dict(self) -> dict[str, Any]:
        return {**self.metadata, "body": self.body, "content_hash": self.hash}


class Vault:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self._assert_vault()

    @classmethod
    def create(cls, root: Path, name: str, world_name: str = "主世界") -> Vault:
        root = root.expanduser().resolve()
        if root.exists() and any(root.iterdir()):
            raise VaultError(f"目标目录不是空目录：{root}")
        root.mkdir(parents=True, exist_ok=True)
        world_slug = safe_slug(world_name, "main-world")
        try:
            cls._atomic_text(
                root / "vault.yaml",
                yaml.safe_dump(
                    {
                        "format": "worldbuilding-vault",
                        "schema_version": 1,
                        "name": name.strip() or "我的世界库",
                        "created_at": utc_local_now(),
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
            )
            world_root = root / "worlds" / world_slug
            (world_root / "pages").mkdir(parents=True, exist_ok=True)
            (world_root / "assets").mkdir(parents=True, exist_ok=True)
            (world_root / "maps").mkdir(parents=True, exist_ok=True)
            cls._atomic_text(
                world_root / "world.yaml",
                yaml.safe_dump(
                    {
                        "id": world_slug,
                        "name": world_name.strip() or "主世界",
                        "default_branch": "main",
                        "created_at": utc_local_now(),
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
            )
            (root / "templates").mkdir(exist_ok=True)
        except Exception:
            if root.exists():
                shutil.rmtree(root)
            raise
        return cls(root)

    def _assert_vault(self) -> None:
        manifest = self.root / "vault.yaml"
        if not manifest.is_file():
            raise VaultError(f"不是有效世界库，缺少 vault.yaml：{self.root}")
        try:
            value = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise VaultError(f"无法读取世界库：{exc}") from exc
        if value.get("format") != "worldbuilding-vault":
            raise VaultError("vault.yaml 的 format 不是 worldbuilding-vault")
        if value.get("schema_version") != 1:
            raise VaultError(f"不支持的世界库 schema：{value.get('schema_version')}")

    @property
    def metadata(self) -> dict[str, Any]:
        return yaml.safe_load((self.root / "vault.yaml").read_text(encoding="utf-8")) or {}

    def worlds(self) -> list[dict[str, Any]]:
        result = []
        for path in sorted((self.root / "worlds").glob("*/world.yaml")):
            value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            value["path"] = str(path.parent.relative_to(self.root))
            result.append(value)
        return result

    def create_world(self, name: str) -> dict[str, Any]:
        title = name.strip()
        if not title:
            raise ValidationError("世界名称不能为空")
        world_id = safe_slug(title, "world")
        existing = {item["id"] for item in self.worlds()}
        if world_id in existing:
            suffix = 2
            base = world_id
            while f"{base}-{suffix}" in existing:
                suffix += 1
            world_id = f"{base}-{suffix}"
        world_root = self.root / "worlds" / world_id
        (world_root / "pages").mkdir(parents=True, exist_ok=False)
        (world_root / "assets").mkdir()
        (world_root / "maps").mkdir()
        self._atomic_text(
            world_root / "world.yaml",
            yaml.safe_dump(
                {
                    "id": world_id,
                    "name": title,
                    "default_branch": "main",
                    "created_at": utc_local_now(),
                },
                allow_unicode=True,
                sort_keys=False,
            ),
        )
        return next(item for item in self.worlds() if item["id"] == world_id)

    def save_asset(self, world: str, filename: str, data: bytes) -> dict[str, str | int]:
        if world not in {item["id"] for item in self.worlds()}:
            raise ValidationError(f"世界不存在：{world}")
        if not data:
            raise ValidationError("附件不能为空")
        if len(data) > MAX_ASSET_BYTES:
            raise ValidationError("单个附件不能超过 50 MiB")
        source_name = Path(filename).name
        if source_name != filename or source_name in {"", ".", ".."}:
            raise ValidationError("附件文件名不合法")
        suffix = Path(source_name).suffix.lower()
        if suffix not in ALLOWED_ASSET_SUFFIXES:
            raise ValidationError("不支持此附件类型：" + (suffix or "无扩展名"))
        stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", Path(source_name).stem).strip("-")
        stem = stem[:80] or "asset"
        stored_name = f"{uuid.uuid4().hex[:8]}-{stem}{suffix}"
        relative = Path("worlds") / world / "assets" / stored_name
        target = self.root / relative
        self._atomic_bytes(target, data)
        return {
            "filename": stored_name,
            "bytes": len(data),
            "vault_path": relative.as_posix(),
            "markdown": f"![{Path(source_name).stem}](../../assets/{stored_name})",
        }

    def read_asset(self, relative_path: str) -> tuple[Path, bytes]:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise VaultError("附件路径不安全")
        if (
            len(path.parts) < 4
            or path.parts[0] != "worlds"
            or path.parts[2]
            not in {
                "assets",
                "maps",
            }
        ):
            raise VaultError("只允许读取世界库中的 assets 或 maps")
        target = self._inside(self.root / path)
        if not target.is_file() or target.is_symlink():
            raise VaultError("附件不存在")
        return target, target.read_bytes()

    def iter_entries(self) -> Iterable[EntryDocument]:
        for path in sorted((self.root / "worlds").glob("*/pages/*/*.md")):
            try:
                yield self.read_path(path)
            except ValidationError:
                continue

    def read_path(self, path: Path) -> EntryDocument:
        safe_path = self._inside(path)
        raw = safe_path.read_bytes()
        metadata, body = parse_markdown(raw.decode("utf-8"))
        self._validate_metadata(metadata)
        return EntryDocument(metadata, body, safe_path, content_hash(raw))

    def find_entry(self, entry_id: str) -> EntryDocument:
        matches = list((self.root / "worlds").glob(f"*/pages/*/{entry_id}.md"))
        if not matches:
            raise VaultError(f"条目不存在：{entry_id}")
        if len(matches) > 1:
            raise VaultError(f"条目 ID 重复：{entry_id}")
        return self.read_path(matches[0])

    def create_entry(self, payload: dict[str, Any]) -> EntryDocument:
        entry_type = str(payload.get("type", "concept"))
        if entry_type not in ENTRY_TYPES:
            raise ValidationError(f"不支持的条目类型：{entry_type}")
        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValidationError("标题不能为空")
        world = str(payload.get("world") or self._default_world())
        if world not in {item["id"] for item in self.worlds()}:
            raise ValidationError(f"世界不存在：{world}")
        entry_id = make_id(entry_type)
        now = utc_local_now()
        metadata = {
            "id": entry_id,
            "type": entry_type,
            "title": title,
            "aliases": self._string_list(payload.get("aliases", [])),
            "world": world,
            "branch": str(payload.get("branch") or "main"),
            "status": str(payload.get("status") or "draft"),
            "tags": self._string_list(payload.get("tags", [])),
            "relations": payload.get("relations") or [],
            "created_at": now,
            "updated_at": now,
        }
        if payload.get("time"):
            metadata["time"] = payload["time"]
        if payload.get("claims"):
            metadata["claims"] = payload["claims"]
        self._validate_metadata(metadata)
        path = self.root / "worlds" / world / "pages" / entry_type / f"{entry_id}.md"
        self._atomic_text(path, dump_markdown(metadata, str(payload.get("body") or "")))
        return self.read_path(path)

    def update_entry(
        self, entry_id: str, payload: dict[str, Any], expected_hash: str | None
    ) -> EntryDocument:
        current = self.find_entry(entry_id)
        if expected_hash and current.hash != expected_hash:
            raise ConflictError("条目已被其他编辑器或页面修改，请重新加载后比较")
        metadata = dict(current.metadata)
        for key in (
            "title",
            "aliases",
            "status",
            "tags",
            "branch",
            "relations",
            "time",
            "claims",
        ):
            if key in payload:
                metadata[key] = payload[key]
        metadata["title"] = str(metadata.get("title", "")).strip()
        metadata["aliases"] = self._string_list(metadata.get("aliases", []))
        metadata["tags"] = self._string_list(metadata.get("tags", []))
        metadata["updated_at"] = utc_local_now()
        self._validate_metadata(metadata)
        body = str(payload.get("body", current.body))
        self._atomic_text(current.path, dump_markdown(metadata, body))
        return self.read_path(current.path)

    def archive_entry(self, entry_id: str, expected_hash: str | None = None) -> EntryDocument:
        return self.update_entry(entry_id, {"status": "deprecated"}, expected_hash)

    def _default_world(self) -> str:
        worlds = self.worlds()
        if not worlds:
            raise VaultError("世界库中没有世界")
        return str(worlds[0]["id"])

    def _inside(self, path: Path) -> Path:
        resolved = path.expanduser().resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise VaultError("路径逃出了世界库") from exc
        return resolved

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part.strip() for part in value.split(",")]
        if not isinstance(value, list):
            raise ValidationError("别名和标签必须是字符串列表")
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @staticmethod
    def _validate_metadata(metadata: dict[str, Any]) -> None:
        required = ("id", "type", "title", "status", "world")
        missing = [key for key in required if not metadata.get(key)]
        if missing:
            raise ValidationError("缺少必填元数据：" + ", ".join(missing))
        if not VALID_ID_RE.fullmatch(str(metadata["id"])):
            raise ValidationError(f"条目 ID 格式不合法：{metadata['id']}")
        if metadata["type"] not in ENTRY_TYPES:
            raise ValidationError(f"条目类型不合法：{metadata['type']}")
        if metadata["status"] not in ENTRY_STATUSES:
            raise ValidationError(f"条目状态不合法：{metadata['status']}")
        if not isinstance(metadata.get("relations", []), list):
            raise ValidationError("relations 必须是列表")
        time_value = metadata.get("time")
        if time_value is not None:
            if not isinstance(time_value, dict):
                raise ValidationError("time 必须是对象")
            earliest = time_value.get("earliest_ordinal")
            latest = time_value.get("latest_ordinal")
            if earliest is not None and latest is not None and earliest > latest:
                raise ValidationError("time 的 earliest_ordinal 不能晚于 latest_ordinal")

    @staticmethod
    def _atomic_text(path: Path, text: str) -> None:
        Vault._atomic_bytes(path, text.encode("utf-8"))

    @staticmethod
    def _atomic_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
