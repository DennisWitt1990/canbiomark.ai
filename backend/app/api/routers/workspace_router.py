"""Download endpoint shared by every module.

Instead of one download route per module, there is a single one: it takes a
path relative to the caller's workspace and serves the file if — and only if —
the path resolves inside that workspace.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from ...domain.errors import ResourceNotFoundError
from ...services.workspace_service import UserWorkspace
from ..dependencies import get_current_workspace

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/download")
def download_workspace_file(
    path: str = Query(..., description="Path relative to your workspace."),
    workspace: UserWorkspace = Depends(get_current_workspace),
) -> FileResponse:
    """Serve one file out of the caller's own workspace."""
    target_path = workspace.resolve(path)
    if not target_path.is_file():
        raise ResourceNotFoundError("The requested path is not a file.")
    return FileResponse(path=str(target_path), filename=target_path.name)


@router.get("/files")
def list_workspace_files(
    directory: str = Query(default=".", description="Directory relative to your workspace."),
    workspace: UserWorkspace = Depends(get_current_workspace),
) -> dict:
    """List every file below a directory of the caller's workspace."""
    target_directory = (
        workspace.root_directory
        if directory in (".", "", "/")
        else workspace.resolve(directory)
    )
    return {
        "directory": workspace.to_relative_path(target_directory),
        "files": workspace.list_files_recursively(target_directory),
        "used_bytes": workspace.used_bytes(),
    }
