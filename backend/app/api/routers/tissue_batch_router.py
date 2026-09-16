"""Synthetic tissue generation with SimBu: batch runs."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

from ...container import ServiceContainer
from ...services.workspace_service import UserWorkspace
from ..dependencies import get_container, get_current_user, get_current_workspace
from ..schemas.authentication_schemas import SimpleAcknowledgement
from ..schemas.tissue_schemas import (
    BatchDefinitionResponse,
    BatchJobResponse,
    StartBatchRequest,
)

router = APIRouter(
    prefix="/tissue-batches",
    tags=["tissue batches"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/definitions", response_model=BatchDefinitionResponse)
async def upload_batch_definition(
    file: UploadFile = File(..., description="A .csv or .tsv batch definition."),
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> BatchDefinitionResponse:
    """Validate a batch definition without starting anything (dry run)."""
    raw_bytes = await file.read()
    preview = container.tissue_batch_service.store_definition_file(
        workspace, file.filename or "", raw_bytes
    )
    return BatchDefinitionResponse(
        definition_path=preview.definition_relative_path,
        row_count=preview.row_count,
        planned_task_count=preview.planned_task_count,
    )


@router.post("/jobs", response_model=BatchJobResponse, status_code=202)
def start_batch_job(
    start_request: StartBatchRequest,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> BatchJobResponse:
    """Queue every simulation described by a previously uploaded definition."""
    job = container.tissue_batch_service.start_batch(
        workspace, start_request.definition_path
    )
    return BatchJobResponse.from_job(job)


@router.get("/jobs", response_model=List[BatchJobResponse])
def list_batch_jobs(
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> List[BatchJobResponse]:
    """All batches of the caller, newest first, without the task details."""
    jobs = container.tissue_batch_service.list_jobs(workspace)
    return [BatchJobResponse.from_job(job, include_tasks=False) for job in jobs]


@router.get("/jobs/{job_id}", response_model=BatchJobResponse)
def get_batch_job(
    job_id: str,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> BatchJobResponse:
    """Status of one batch including every task."""
    job = container.tissue_batch_service.get_job(workspace, job_id)
    return BatchJobResponse.from_job(job)


@router.get("/jobs/{job_id}/archive")
def download_batch_archive(
    job_id: str,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> FileResponse:
    """Zip every result of a finished batch and serve it."""
    archive_path = container.tissue_batch_service.build_result_archive(
        workspace, job_id
    )
    return FileResponse(
        path=str(archive_path),
        filename=f"simbu_batch_{job_id[:8]}.zip",
        media_type="application/zip",
    )


@router.delete("/jobs/{job_id}", response_model=SimpleAcknowledgement)
def cancel_batch_job(
    job_id: str,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> SimpleAcknowledgement:
    """Cancel a running batch and remove its results from disk."""
    container.tissue_batch_service.cancel_and_delete(workspace, job_id)
    return SimpleAcknowledgement(message="The batch was cancelled and removed.")
