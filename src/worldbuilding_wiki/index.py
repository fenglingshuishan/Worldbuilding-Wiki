from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from worldbuilding_wiki.errors import ValidationError
from worldbuilding_wiki.store import Vault, extract_wiki_links


def index_path(runtime_root: Path, vault_path: Path) -> Path:
    digest = hashlib.sha256(str(vault_path.resolve()).encode()).hexdigest()[:16]
    target = runtime_root / "indexes" / f"{digest}.sqlite"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


class VaultIndex:
    def __init__(self, database: Path):
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    world TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    aliases TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    body TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS links (
                    source_id TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    target_id TEXT,
                    label TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_id);
                CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_id);
                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    valid_from TEXT,
                    valid_to TEXT,
                    branch TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations(subject);
                CREATE INDEX IF NOT EXISTS idx_relations_object ON relations(object);
                CREATE TABLE IF NOT EXISTS checks (
                    rule_id TEXT NOT NULL,
                    entry_id TEXT,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    evidence TEXT NOT NULL
                );
                """
            )
            try:
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5("
                    "id UNINDEXED, title, aliases, body, tokenize='unicode61')"
                )
            except sqlite3.OperationalError:
                pass

    def rebuild(self, vault: Vault) -> dict[str, int]:
        raw_documents = []
        invalid_files = []
        for path in vault.entry_paths():
            try:
                raw_documents.append(vault.read_path(path))
            except (OSError, UnicodeDecodeError, ValidationError) as exc:
                invalid_files.append(
                    {"path": path.relative_to(vault.root).as_posix(), "message": str(exc)}
                )
        documents = []
        seen_ids: dict[str, str] = {}
        duplicate_ids = []
        for document in raw_documents:
            entry_id = str(document.metadata["id"])
            relative = document.path.relative_to(vault.root).as_posix()
            if entry_id in seen_ids:
                duplicate_ids.append({"id": entry_id, "paths": [seen_ids[entry_id], relative]})
                continue
            seen_ids[entry_id] = relative
            documents.append(document)
        ids = {str(doc.metadata["id"]): str(doc.metadata["id"]) for doc in documents}
        refs: dict[str, list[str]] = defaultdict(list)
        for doc in documents:
            entry_id = str(doc.metadata["id"])
            refs[str(doc.metadata["title"]).casefold()].append(entry_id)
            for alias in doc.metadata.get("aliases", []):
                refs[str(alias).casefold()].append(entry_id)

        with self.connect() as connection:
            connection.execute("DELETE FROM links")
            connection.execute("DELETE FROM relations")
            connection.execute("DELETE FROM checks")
            connection.execute("DELETE FROM entries")
            try:
                connection.execute("DELETE FROM entries_fts")
            except sqlite3.OperationalError:
                pass

            link_count = 0
            relation_count = 0
            incoming: dict[str, int] = defaultdict(int)
            outgoing: dict[str, int] = defaultdict(int)

            for error in invalid_files:
                self._add_check(
                    connection,
                    "FILE_INVALID",
                    None,
                    "error",
                    f"条目文件无法解析：{error['path']}",
                    error,
                )
            for duplicate in duplicate_ids:
                self._add_check(
                    connection,
                    "ID_DUPLICATE",
                    duplicate["id"],
                    "error",
                    f"条目 ID 重复：{duplicate['id']}",
                    duplicate,
                )

            for reference, candidates in sorted(refs.items()):
                unique_candidates = sorted(set(candidates))
                if len(unique_candidates) > 1:
                    self._add_check(
                        connection,
                        "ALIAS_DUPLICATE",
                        None,
                        "warning",
                        f"标题或别名“{reference}”对应多个条目",
                        {"reference": reference, "candidates": unique_candidates},
                    )

            for doc in documents:
                metadata = doc.metadata
                entry_id = str(metadata["id"])
                aliases = [str(item) for item in metadata.get("aliases", [])]
                tags = [str(item) for item in metadata.get("tags", [])]
                connection.execute(
                    """
                    INSERT INTO entries
                    (id, file_path, type, title, status, world, branch, aliases, tags,
                     body, metadata, content_hash, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        str(doc.path.relative_to(vault.root)),
                        metadata["type"],
                        metadata["title"],
                        metadata["status"],
                        metadata["world"],
                        metadata.get("branch", "main"),
                        json.dumps(aliases, ensure_ascii=False),
                        json.dumps(tags, ensure_ascii=False),
                        doc.body,
                        json.dumps(metadata, ensure_ascii=False),
                        doc.hash,
                        metadata.get("updated_at"),
                    ),
                )
                try:
                    connection.execute(
                        "INSERT INTO entries_fts(id, title, aliases, body) VALUES (?, ?, ?, ?)",
                        (entry_id, metadata["title"], " ".join(aliases), doc.body),
                    )
                except sqlite3.OperationalError:
                    pass

                for link in extract_wiki_links(doc.body):
                    target_ref = link["target"]
                    candidates = (
                        [target_ref] if target_ref in ids else refs.get(target_ref.casefold(), [])
                    )
                    target_id = candidates[0] if len(candidates) == 1 else None
                    connection.execute(
                        "INSERT INTO links(source_id, target_ref, target_id, label) VALUES (?, ?, ?, ?)",
                        (entry_id, target_ref, target_id, link["label"]),
                    )
                    link_count += 1
                    outgoing[entry_id] += 1
                    if target_id:
                        incoming[target_id] += 1
                    elif len(candidates) > 1:
                        self._add_check(
                            connection,
                            "ALIAS_AMBIGUOUS",
                            entry_id,
                            "warning",
                            f"链接“{target_ref}”对应多个条目",
                            {"target_ref": target_ref, "candidates": candidates},
                        )
                    else:
                        self._add_check(
                            connection,
                            "LINK_BROKEN",
                            entry_id,
                            "warning",
                            f"链接目标不存在：{target_ref}",
                            {"target_ref": target_ref},
                        )

                for offset, relation in enumerate(metadata.get("relations", [])):
                    if not isinstance(relation, dict):
                        continue
                    target = str(relation.get("object", "")).strip()
                    predicate = str(relation.get("predicate", "related_to")).strip()
                    if not target:
                        continue
                    relation_id = str(relation.get("id") or f"{entry_id}:{offset}")
                    connection.execute(
                        """
                        INSERT INTO relations
                        (id, subject, predicate, object, valid_from, valid_to, branch, status, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            relation_id,
                            entry_id,
                            predicate,
                            target,
                            json.dumps(relation.get("valid_from"), ensure_ascii=False),
                            json.dumps(relation.get("valid_to"), ensure_ascii=False),
                            relation.get("branch", metadata.get("branch", "main")),
                            relation.get("status", metadata["status"]),
                            str(relation.get("note", "")),
                        ),
                    )
                    relation_count += 1
                    outgoing[entry_id] += 1
                    if target in ids:
                        incoming[target] += 1
                    else:
                        self._add_check(
                            connection,
                            "RELATION_TARGET_MISSING",
                            entry_id,
                            "error",
                            f"关系目标不存在：{target}",
                            {"relation_id": relation_id, "object": target},
                        )

            status_by_id = {str(doc.metadata["id"]): doc.metadata["status"] for doc in documents}
            for row in connection.execute(
                "SELECT source_id, target_id FROM links WHERE target_id IS NOT NULL"
            ):
                if (
                    status_by_id.get(row["source_id"]) == "canon"
                    and status_by_id.get(row["target_id"]) == "deprecated"
                ):
                    self._add_check(
                        connection,
                        "DEPRECATED_REFERENCED",
                        row["source_id"],
                        "warning",
                        f"正史条目引用了废弃条目：{row['target_id']}",
                        {"target_id": row["target_id"]},
                    )

            for doc in documents:
                entry_id = str(doc.metadata["id"])
                if not incoming[entry_id] and not outgoing[entry_id]:
                    self._add_check(
                        connection,
                        "ENTRY_ORPHAN",
                        entry_id,
                        "info",
                        "条目没有入链、出链或关系",
                        {},
                    )

            self._check_relation_times(connection, documents)

        return {
            "entries": len(documents),
            "links": link_count,
            "relations": relation_count,
            "checks": self.check_count(),
        }

    def _check_relation_times(self, connection: sqlite3.Connection, documents: list[Any]) -> None:
        times = {
            str(doc.metadata["id"]): self._time_bounds(doc.metadata.get("time"))
            for doc in documents
        }
        titles = {str(doc.metadata["id"]): str(doc.metadata["title"]) for doc in documents}
        ordered = connection.execute(
            "SELECT id, subject, predicate, object FROM relations "
            "WHERE predicate IN ('causes', 'precedes')"
        ).fetchall()
        for relation in ordered:
            before = times.get(relation["subject"])
            after = times.get(relation["object"])
            if not before or not after:
                continue
            if before[0] > after[1]:
                self._add_check(
                    connection,
                    "EVENT_ORDER_INVALID",
                    relation["subject"],
                    "error",
                    f"“{titles.get(relation['subject'], relation['subject'])}”被声明为"
                    f"{relation['predicate']}“{titles.get(relation['object'], relation['object'])}”，"
                    "但时间范围确定晚于目标",
                    {"relation_id": relation["id"], "subject_time": before, "object_time": after},
                )

        locations: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in connection.execute(
            "SELECT id, subject, object, valid_from, valid_to FROM relations "
            "WHERE predicate = 'located_in'"
        ):
            locations[row["subject"]].append(row)
        for subject, rows in locations.items():
            for left, right in combinations(rows, 2):
                if left["object"] == right["object"]:
                    continue
                left_range = self._relation_bounds(left)
                right_range = self._relation_bounds(right)
                if left_range and right_range and self._overlaps(left_range, right_range):
                    self._add_check(
                        connection,
                        "LOCATION_CONFLICT",
                        subject,
                        "warning",
                        "同一条目在重叠时间内具有多个 located_in 关系",
                        {
                            "relations": [left["id"], right["id"]],
                            "locations": [left["object"], right["object"]],
                            "ranges": [left_range, right_range],
                        },
                    )

    @staticmethod
    def _time_bounds(value: Any) -> tuple[float, float] | None:
        if not isinstance(value, dict):
            return None
        earliest = value.get("earliest_ordinal")
        latest = value.get("latest_ordinal")
        if earliest is None and latest is None:
            return None
        start = float(earliest if earliest is not None else latest)
        end = float(latest if latest is not None else earliest)
        return start, end

    @classmethod
    def _relation_bounds(cls, row: sqlite3.Row) -> tuple[float, float] | None:
        def load(raw: str | None) -> Any:
            return json.loads(raw) if raw else None

        start_value = load(row["valid_from"])
        end_value = load(row["valid_to"])
        start_bounds = cls._time_bounds(start_value)
        end_bounds = cls._time_bounds(end_value)
        if start_bounds and end_bounds:
            return start_bounds[0], end_bounds[1]
        if start_bounds:
            return start_bounds
        if end_bounds:
            return end_bounds
        if isinstance(start_value, (int, float)) and isinstance(end_value, (int, float)):
            return float(start_value), float(end_value)
        return None

    @staticmethod
    def _overlaps(left: tuple[float, float], right: tuple[float, float]) -> bool:
        return max(left[0], right[0]) <= min(left[1], right[1])

    @staticmethod
    def _add_check(
        connection: sqlite3.Connection,
        rule_id: str,
        entry_id: str | None,
        severity: str,
        message: str,
        evidence: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO checks(rule_id, entry_id, severity, message, evidence) VALUES (?, ?, ?, ?, ?)",
            (rule_id, entry_id, severity, message, json.dumps(evidence, ensure_ascii=False)),
        )

    def list_entries(
        self,
        *,
        query: str = "",
        entry_type: str = "",
        status: str = "",
        world: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = []
        values: list[Any] = []
        if query.strip():
            value = f"%{query.strip()}%"
            clauses.append("(title LIKE ? OR aliases LIKE ? OR body LIKE ? OR tags LIKE ?)")
            values.extend((value, value, value, value))
        if entry_type:
            clauses.append("type = ?")
            values.append(entry_type)
        if status:
            clauses.append("status = ?")
            values.append(status)
        if world:
            clauses.append("world = ?")
            values.append(world)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(max(1, min(limit, 1000)))
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, type, title, status, world, branch, aliases, tags, updated_at "
                f"FROM entries{where} ORDER BY updated_at DESC, title LIMIT ?",
                values,
            ).fetchall()
        return [self._entry_summary(row) for row in rows]

    def entry_context(self, entry_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            backlinks = connection.execute(
                """
                SELECT e.id, e.type, e.title, e.status
                FROM links l JOIN entries e ON e.id = l.source_id
                WHERE l.target_id = ? ORDER BY e.title
                """,
                (entry_id,),
            ).fetchall()
            links = connection.execute(
                """
                SELECT l.target_ref, l.target_id, l.label, e.title, e.type, e.status
                FROM links l LEFT JOIN entries e ON e.id = l.target_id
                WHERE l.source_id = ?
                """,
                (entry_id,),
            ).fetchall()
            relations = connection.execute(
                """
                SELECT r.*, e.title AS object_title, e.type AS object_type
                FROM relations r LEFT JOIN entries e ON e.id = r.object
                WHERE r.subject = ? OR r.object = ? ORDER BY r.predicate
                """,
                (entry_id, entry_id),
            ).fetchall()
            checks = connection.execute(
                "SELECT * FROM checks WHERE entry_id = ? ORDER BY severity, rule_id", (entry_id,)
            ).fetchall()
        return {
            "backlinks": [dict(row) for row in backlinks],
            "links": [dict(row) for row in links],
            "relations": [self._relation(row) for row in relations],
            "checks": [self._check(row) for row in checks],
        }

    def list_checks(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*, e.title AS entry_title, e.type AS entry_type
                FROM checks c LEFT JOIN entries e ON e.id = c.entry_id
                ORDER BY CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                         rule_id, entry_title
                """
            ).fetchall()
        return [self._check(row) for row in rows]

    def check_count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM checks").fetchone()[0])

    def timeline(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, type, title, status, world, branch, metadata FROM entries"
            ).fetchall()
        result = []
        for row in rows:
            metadata = json.loads(row["metadata"])
            time_value = metadata.get("time")
            if not isinstance(time_value, dict):
                continue
            result.append(
                {
                    "id": row["id"],
                    "type": row["type"],
                    "title": row["title"],
                    "status": row["status"],
                    "world": row["world"],
                    "branch": row["branch"],
                    "time": time_value,
                }
            )
        result.sort(
            key=lambda item: (
                item["time"].get("earliest_ordinal") is None,
                item["time"].get("earliest_ordinal", 0),
                item["title"],
            )
        )
        return result

    def dashboard(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, type, title, status, world, branch, aliases, tags, body, updated_at "
                "FROM entries ORDER BY updated_at DESC, title"
            ).fetchall()
            check_rows = connection.execute(
                "SELECT severity, COUNT(*) AS count FROM checks GROUP BY severity"
            ).fetchall()
            relation_count = int(connection.execute("SELECT COUNT(*) FROM relations").fetchone()[0])
            link_count = int(connection.execute("SELECT COUNT(*) FROM links").fetchone()[0])

        by_status: dict[str, int] = defaultdict(int)
        by_type: dict[str, int] = defaultdict(int)
        by_world: dict[str, int] = defaultdict(int)
        tags: dict[str, int] = defaultdict(int)
        branches = set()
        developed = 0
        needs_attention = []
        summaries = []
        for row in rows:
            summary = self._entry_summary(row)
            summary.pop("body", None)
            summaries.append(summary)
            by_status[row["status"]] += 1
            by_type[row["type"]] += 1
            by_world[row["world"]] += 1
            branches.add((row["world"], row["branch"]))
            for tag in summary["tags"]:
                tags[tag] += 1
            has_body = len(str(row["body"]).strip()) >= 80
            has_structure = bool(summary["tags"] or summary["aliases"])
            if has_body and has_structure:
                developed += 1
            if row["status"] == "draft" or not has_body:
                needs_attention.append(
                    {**summary, "reason": "待确认草稿" if row["status"] == "draft" else "正文较短"}
                )

        total = len(rows)
        return {
            "summary": {
                "entries": total,
                "canonical": by_status.get("canon", 0),
                "drafts": by_status.get("draft", 0),
                "relations": relation_count,
                "links": link_count,
                "branches": len(branches),
                "content_health": round(developed * 100 / total) if total else 0,
            },
            "by_status": dict(sorted(by_status.items())),
            "by_type": dict(sorted(by_type.items(), key=lambda item: (-item[1], item[0]))),
            "by_world": dict(sorted(by_world.items(), key=lambda item: (-item[1], item[0]))),
            "checks": {row["severity"]: row["count"] for row in check_rows},
            "top_tags": [
                {"name": name, "count": count}
                for name, count in sorted(tags.items(), key=lambda item: (-item[1], item[0]))[:10]
            ],
            "recent": summaries[:8],
            "needs_attention": needs_attention[:8],
        }

    def graph(self, entry_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            root = connection.execute(
                "SELECT id, type, title, status FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if not root:
                return {"nodes": [], "edges": []}
            rows = connection.execute(
                """
                SELECT subject, predicate, object FROM relations
                WHERE subject = ? OR object = ?
                """,
                (entry_id, entry_id),
            ).fetchall()
            link_rows = connection.execute(
                "SELECT source_id, target_id FROM links WHERE source_id = ? OR target_id = ?",
                (entry_id, entry_id),
            ).fetchall()
            node_ids = {entry_id}
            edges = []
            for row in rows:
                node_ids.update((row["subject"], row["object"]))
                edges.append(
                    {"source": row["subject"], "target": row["object"], "label": row["predicate"]}
                )
            for row in link_rows:
                if row["target_id"]:
                    node_ids.update((row["source_id"], row["target_id"]))
                    edges.append(
                        {"source": row["source_id"], "target": row["target_id"], "label": "提及"}
                    )
            placeholders = ",".join("?" for _ in node_ids)
            nodes = connection.execute(
                f"SELECT id, type, title, status FROM entries WHERE id IN ({placeholders})",
                tuple(node_ids),
            ).fetchall()
        return {"nodes": [dict(row) for row in nodes], "edges": edges}

    def graph_overview(self, limit: int = 250) -> dict[str, Any]:
        limit = max(1, min(limit, 500))
        with self.connect() as connection:
            nodes = connection.execute(
                "SELECT id, type, title, status, world FROM entries "
                "ORDER BY updated_at DESC, title LIMIT ?",
                (limit,),
            ).fetchall()
            node_ids = {row["id"] for row in nodes}
            relation_rows = connection.execute(
                "SELECT subject, predicate, object FROM relations ORDER BY predicate"
            ).fetchall()
            link_rows = connection.execute(
                "SELECT source_id, target_id FROM links WHERE target_id IS NOT NULL"
            ).fetchall()
        edges = [
            {
                "source": row["subject"],
                "target": row["object"],
                "label": row["predicate"],
                "kind": "relation",
            }
            for row in relation_rows
            if row["subject"] in node_ids and row["object"] in node_ids
        ]
        edges.extend(
            {
                "source": row["source_id"],
                "target": row["target_id"],
                "label": "提及",
                "kind": "link",
            }
            for row in link_rows
            if row["source_id"] in node_ids and row["target_id"] in node_ids
        )
        return {"nodes": [dict(row) for row in nodes], "edges": edges}

    @staticmethod
    def _entry_summary(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["aliases"] = json.loads(value["aliases"])
        value["tags"] = json.loads(value["tags"])
        return value

    @staticmethod
    def _check(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["evidence"] = json.loads(value["evidence"])
        return value

    @staticmethod
    def _relation(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        for key in ("valid_from", "valid_to"):
            value[key] = json.loads(value[key]) if value[key] else None
        return value
