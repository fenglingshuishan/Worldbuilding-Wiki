from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from worldbuilding_wiki import __version__
from worldbuilding_wiki.errors import (
    ConflictError,
    TransferError,
    ValidationError,
    VaultError,
    WorldbuildingWikiError,
)
from worldbuilding_wiki.resources import sample_data_dir, static_dir
from worldbuilding_wiki.service import WorldbuildingService


class VaultCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    world_name: str = Field(default="主世界", min_length=1, max_length=100)
    path: str | None = None
    include_sample: bool = True


class VaultOpenRequest(BaseModel):
    path: str


class VaultDeleteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)


class WorldCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class EntryWriteRequest(BaseModel):
    title: str
    type: str = "concept"
    status: str = "draft"
    world: str | None = None
    branch: str = "main"
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    body: str = ""
    relations: list[dict[str, Any]] = Field(default_factory=list)
    time: dict[str, Any] | None = None
    claims: list[dict[str, Any]] | None = None
    template_id: str | None = None
    template_version: int | None = None
    custom_fields: dict[str, Any] | None = None
    expected_hash: str | None = None


class ExportRequest(BaseModel):
    scope: str = "vault"
    world_ids: list[str] = Field(default_factory=list)


class ImportCommitRequest(BaseModel):
    conflict_choices: dict[str, str] = Field(default_factory=dict)


class TemplateWriteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    type: str = "concept"
    status: str = "draft"
    tags: list[str] = Field(default_factory=list)
    body: str = ""
    fields: list[dict[str, Any]] = Field(default_factory=list)
    expected_version: int | None = None


class TemplateMigrationRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=200)
    target_template_id: str
    field_mapping: dict[str, str] = Field(default_factory=dict)


class BulkEntryRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=200)
    status: str | None = None
    add_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)


class EntryRestoreRequest(BaseModel):
    revision_id: str
    expected_hash: str | None = None


class MapWriteRequest(BaseModel):
    name: str | None = None
    layers: list[dict[str, Any]] | None = None
    markers: list[dict[str, Any]] | None = None
    expected_hash: str | None = None


class BranchVariantRequest(BaseModel):
    target_branch: str


class BranchMergeRequest(BaseModel):
    base_branch: str
    target_branch: str
    decisions: dict[str, str] = Field(default_factory=dict)


class AIProposalRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=20)
    instruction: str = Field(min_length=1, max_length=2000)


def create_app(service: WorldbuildingService) -> FastAPI:
    app = FastAPI(
        title="Worldbuilding Wiki",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.service = service

    @app.exception_handler(WorldbuildingWikiError)
    async def handle_expected_error(_: Request, exc: WorldbuildingWikiError) -> JSONResponse:
        status = 409 if isinstance(exc, (ConflictError, VaultError)) else 400
        if isinstance(exc, ValidationError):
            status = 422
        if isinstance(exc, TransferError):
            status = 400
        return JSONResponse(
            {"error": exc.__class__.__name__, "message": str(exc)}, status_code=status
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": "RequestValidationError",
                "message": "请求字段不合法",
                "details": exc.errors(),
            },
            status_code=422,
        )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "ready": service.info()["ready"]}

    @app.get("/api/info")
    async def info() -> dict[str, Any]:
        return service.info()

    @app.get("/api/dashboard")
    async def dashboard() -> dict[str, Any]:
        return service.dashboard()

    @app.get("/api/diagnostics")
    async def diagnostics() -> dict[str, Any]:
        return service.diagnostics()

    @app.get("/api/ai/info")
    async def ai_info() -> dict[str, Any]:
        return service.ai_info()

    @app.post("/api/ai/scope")
    async def preview_ai_scope(request: AIProposalRequest) -> dict[str, Any]:
        return service.preview_ai_scope(request.entry_ids, request.instruction)

    @app.post("/api/ai/proposals")
    async def generate_ai_proposal(request: AIProposalRequest) -> dict[str, Any]:
        return service.generate_ai_proposal(request.entry_ids, request.instruction)

    @app.get("/api/ai/proposals")
    async def ai_proposals() -> list[dict[str, Any]]:
        return service.list_ai_proposals()

    @app.delete("/api/ai/proposals/{proposal_id}")
    async def delete_ai_proposal(proposal_id: str) -> dict[str, str]:
        return service.delete_ai_proposal(proposal_id)

    @app.post("/api/application/exit")
    async def exit_application() -> dict[str, bool]:
        callback = getattr(app.state, "shutdown_callback", None)
        if callback:
            callback()
        return {"accepted": bool(callback)}

    @app.post("/api/vaults")
    async def create_vault(request: VaultCreateRequest) -> dict[str, Any]:
        return service.create_vault(
            request.name,
            request.world_name,
            Path(request.path) if request.path else None,
            include_sample=request.include_sample,
        )

    @app.post("/api/vaults/open")
    async def open_vault(request: VaultOpenRequest) -> dict[str, Any]:
        return service.open_vault(Path(request.path))

    @app.post("/api/vaults/close")
    async def close_vault() -> dict[str, Any]:
        return service.close_vault()

    @app.delete("/api/vaults/current")
    async def delete_vault(request: VaultDeleteRequest) -> dict[str, Any]:
        return service.delete_vault(request.confirmation)

    @app.post("/api/worlds")
    async def create_world(request: WorldCreateRequest) -> dict[str, Any]:
        return service.create_world(request.name)

    @app.get("/api/sample")
    async def sample() -> dict[str, Any]:
        return service.sample_status()

    @app.post("/api/sample/restore")
    async def restore_sample_data() -> dict[str, Any]:
        return service.restore_sample()

    @app.delete("/api/sample")
    async def delete_sample_data() -> dict[str, Any]:
        return service.delete_sample()

    @app.post("/api/reindex")
    async def reindex() -> dict[str, int]:
        return service.reindex()

    @app.get("/api/entries")
    async def entries(
        q: str = "",
        type: str = "",
        status: str = "",
        world: str = "",
        limit: int = Query(200, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        return service.list_entries(
            query=q, entry_type=type, status=status, world=world, limit=limit
        )

    @app.post("/api/entries")
    async def create_entry(request: EntryWriteRequest) -> dict[str, Any]:
        return service.create_entry(
            request.model_dump(exclude={"expected_hash"}, exclude_none=True)
        )

    @app.post("/api/entries/bulk")
    async def bulk_entries(request: BulkEntryRequest) -> dict[str, Any]:
        return service.bulk_update_entries(
            request.entry_ids,
            status=request.status,
            add_tags=request.add_tags,
            remove_tags=request.remove_tags,
        )

    @app.get("/api/entries/{entry_id}")
    async def get_entry(entry_id: str) -> dict[str, Any]:
        return service.get_entry(entry_id)

    @app.get("/api/entries/{entry_id}/history")
    async def entry_history(entry_id: str) -> dict[str, Any]:
        return service.entry_history(entry_id)

    @app.get("/api/entries/{entry_id}/diff")
    async def entry_diff(
        entry_id: str, revision_id: str, against_revision_id: str | None = None
    ) -> dict[str, Any]:
        return service.entry_diff(entry_id, revision_id, against_revision_id)

    @app.post("/api/entries/{entry_id}/restore")
    async def restore_entry(entry_id: str, request: EntryRestoreRequest) -> dict[str, Any]:
        return service.restore_entry(entry_id, request.revision_id, request.expected_hash)

    @app.put("/api/entries/{entry_id}")
    async def update_entry(entry_id: str, request: EntryWriteRequest) -> dict[str, Any]:
        payload = request.model_dump(
            exclude={"expected_hash", "type", "world", "template_id", "template_version"},
            exclude_none=True,
        )
        return service.update_entry(entry_id, payload, request.expected_hash)

    @app.delete("/api/entries/{entry_id}")
    async def archive_entry(entry_id: str, expected_hash: str | None = None) -> dict[str, Any]:
        return service.archive_entry(entry_id, expected_hash)

    @app.get("/api/checks")
    async def checks() -> list[dict[str, Any]]:
        return service.checks()

    @app.get("/api/timeline")
    async def timeline() -> list[dict[str, Any]]:
        return service.timeline()

    @app.get("/api/branches")
    async def branches() -> list[str]:
        return service.list_branches()

    @app.post("/api/branches/variants/{entry_id}")
    async def create_branch_variant(entry_id: str, request: BranchVariantRequest) -> dict[str, Any]:
        return service.create_branch_variant(entry_id, request.target_branch)

    @app.get("/api/branches/compare")
    async def compare_branches(base_branch: str, target_branch: str) -> dict[str, Any]:
        return service.compare_branches(base_branch, target_branch)

    @app.post("/api/branches/merge")
    async def merge_branches(request: BranchMergeRequest) -> dict[str, Any]:
        return service.merge_branches(request.base_branch, request.target_branch, request.decisions)

    @app.get("/api/graph/{entry_id}")
    async def graph(entry_id: str) -> dict[str, Any]:
        return service.graph(entry_id)

    @app.get("/api/graph")
    async def graph_overview(limit: int = Query(250, ge=1, le=500)) -> dict[str, Any]:
        return service.graph_overview(limit)

    @app.get("/api/templates")
    async def templates() -> list[dict[str, Any]]:
        return service.list_templates()

    @app.get("/api/templates/{template_id}/versions/{version}")
    async def template_version(template_id: str, version: int) -> dict[str, Any]:
        return service.get_template_version(template_id, version)

    @app.post("/api/templates")
    async def create_template(request: TemplateWriteRequest) -> dict[str, Any]:
        return service.create_template(request.model_dump(exclude={"expected_version"}))

    @app.put("/api/templates/{template_id}")
    async def update_template(template_id: str, request: TemplateWriteRequest) -> dict[str, Any]:
        return service.update_template(template_id, request.model_dump())

    @app.post("/api/templates/migration/preview")
    async def preview_template_migration(request: TemplateMigrationRequest) -> dict[str, Any]:
        return service.preview_template_migration(
            request.entry_ids, request.target_template_id, request.field_mapping
        )

    @app.post("/api/templates/migration/apply")
    async def apply_template_migration(request: TemplateMigrationRequest) -> dict[str, Any]:
        return service.migrate_template_entries(
            request.entry_ids, request.target_template_id, request.field_mapping
        )

    @app.delete("/api/templates/{template_id}")
    async def delete_template(template_id: str) -> dict[str, Any]:
        return service.delete_template(template_id)

    @app.get("/api/maps")
    async def maps(world: str = "") -> list[dict[str, Any]]:
        return service.list_maps(world)

    @app.post("/api/maps")
    async def create_map(request: Request, world: str, name: str, filename: str) -> dict[str, Any]:
        return service.create_map(world, name, filename, await request.body())

    @app.put("/api/maps/{map_id}")
    async def update_map(map_id: str, request: MapWriteRequest) -> dict[str, Any]:
        payload = request.model_dump(exclude={"expected_hash"}, exclude_none=True)
        return service.update_map(map_id, payload, request.expected_hash)

    @app.delete("/api/maps/{map_id}")
    async def delete_map(map_id: str, expected_hash: str | None = None) -> dict[str, str]:
        return service.delete_map(map_id, expected_hash)

    @app.post("/api/assets")
    async def save_asset(request: Request, world: str, filename: str) -> dict[str, Any]:
        return service.save_asset(world, filename, await request.body())

    @app.get("/api/vault-assets/{asset_path:path}", include_in_schema=False)
    async def get_asset(asset_path: str) -> Response:
        path, data = service.read_asset(asset_path)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return Response(data, media_type=media_type)

    @app.post("/api/export/worldvault")
    async def export_worldvault(request: ExportRequest) -> Response:
        path = service.export_worldvault(request.scope, request.world_ids)
        return _download(path, "application/zip")

    @app.post("/api/export/review")
    async def export_review() -> Response:
        path = service.export_review()
        return _download(path, "application/zip")

    @app.post("/api/import/preview")
    async def preview_import(
        request: Request,
        mode: str = Query("merge", pattern="^(new|merge)$"),
        new_vault_name: str = "导入的世界库",
        target_path: str | None = None,
    ) -> dict[str, Any]:
        body = await request.body()
        if not body:
            raise TransferError("没有收到世界传输包")
        return service.preview_import(
            body,
            mode=mode,
            new_vault_name=new_vault_name,
            target_path=target_path,
        )

    @app.post("/api/import/{token}/commit")
    async def commit_import(token: str, request: ImportCommitRequest) -> dict[str, Any]:
        return service.commit_import(token, request.conflict_choices)

    @app.get("/assets/{asset_name}", include_in_schema=False)
    async def application_asset(asset_name: str) -> Response:
        media_types = {
            "app.css": "text/css; charset=utf-8",
            "app.js": "text/javascript; charset=utf-8",
            "sample-tidal-map.webp": "image/webp",
        }
        if asset_name not in media_types:
            raise HTTPException(status_code=404)
        asset_path = (
            sample_data_dir() / "tidal-archive-map.webp"
            if asset_name == "sample-tidal-map.webp"
            else static_dir() / asset_name
        )
        return Response(
            asset_path.read_bytes(),
            media_type=media_types[asset_name],
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/{path:path}", include_in_schema=False)
    async def application_shell(path: str) -> Response:
        return Response(
            (static_dir() / "index.html").read_bytes(),
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    return app


def _download(path: Path, media_type: str) -> Response:
    try:
        data = path.read_bytes()
    finally:
        path.unlink(missing_ok=True)
    encoded_name = path.name.encode("utf-8").hex()
    return Response(
        data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="worldwiki-{encoded_name}.zip"; '
            f"filename*=UTF-8''{_quote_filename(path.name)}"
        },
    )


def _quote_filename(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")
