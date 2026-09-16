"""The AI suite: create a job, upload train/test folders, run, fetch results."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...container import ServiceContainer
from ...services.workspace_service import UserWorkspace
from ..dependencies import get_container, get_current_user, get_current_workspace
from ...domain.analysis_task import AnalysisTask, RegressionModelKind
from ..schemas.ai_suite_schemas import (
    AiSuiteJobResponse,
    AiSuiteOptionsResponse,
    AiSuiteResultsResponse,
    AiSuiteUploadResponse,
    AnalysisTaskOptionResponse,
    CreateAiSuiteJobRequest,
)

router = APIRouter(
    prefix="/ai-suite",
    tags=["ai suite"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/jobs", response_model=AiSuiteJobResponse, status_code=201)
def create_job(
    create_request: CreateAiSuiteJobRequest,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> AiSuiteJobResponse:
    """Create the job folders; uploads and the run follow afterwards."""
    job = container.ai_suite_service.create_job(
        workspace,
        create_request.run_name,
        task=create_request.parsed_task(),
        regression_models=create_request.parsed_regression_models(),
    )
    return AiSuiteJobResponse.from_job(job)


@router.get("/options", response_model=AiSuiteOptionsResponse)
def read_options(
    container: ServiceContainer = Depends(get_container),
) -> AiSuiteOptionsResponse:
    """The tasks and estimators this installation offers, for the run form."""
    return AiSuiteOptionsResponse(
        tasks=[
            AnalysisTaskOptionResponse(
                value=AnalysisTask.CLASSIFICATION.value,
                display_name="Classification (per threshold)",
            ),
            AnalysisTaskOptionResponse(
                value=AnalysisTask.REGRESSION.value,
                display_name="Regression (continuous fraction)",
            ),
        ],
        regression_models=[
            AnalysisTaskOptionResponse(
                value=model.value, display_name=model.display_name
            )
            for model in RegressionModelKind
        ],
        classification_thresholds=list(container.ai_suite_service.thresholds),
    )


@router.get("/jobs", response_model=List[AiSuiteJobResponse])
def list_jobs(
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> List[AiSuiteJobResponse]:
    """All AI suite jobs of the caller, newest first."""
    jobs = container.ai_suite_service.list_jobs(workspace)
    return [AiSuiteJobResponse.from_job(job) for job in jobs]


@router.post("/jobs/{job_id}/uploads", response_model=AiSuiteUploadResponse)
def upload_samples(
    job_id: str,
    split: str = Form(..., description="Either 'train' or 'test'."),
    files: List[UploadFile] = File(...),
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> AiSuiteUploadResponse:
    """Store one uploaded folder.

    Browsers send directory uploads with a relative path in ``filename``; that
    structure is preserved below the split folder.
    """
    ai_suite_service = container.ai_suite_service
    job = ai_suite_service.get_job(workspace, job_id)

    uploaded_file_count = 0
    for uploaded_file in files:
        ai_suite_service.store_uploaded_sample(
            workspace, job, split, uploaded_file.filename or "", uploaded_file.file
        )
        uploaded_file_count += 1

    return AiSuiteUploadResponse(
        job_id=job_id, split=split, uploaded_file_count=uploaded_file_count
    )


@router.post("/jobs/{job_id}/run", response_model=AiSuiteJobResponse, status_code=202)
def start_run(
    job_id: str,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> AiSuiteJobResponse:
    """Queue the benchmarking pipeline for a job whose uploads are complete."""
    ai_suite_service = container.ai_suite_service
    job = ai_suite_service.get_job(workspace, job_id)
    ai_suite_service.start_run(workspace, job)
    return AiSuiteJobResponse.from_job(
        ai_suite_service.get_job(workspace, job_id)
    )


@router.get("/jobs/{job_id}", response_model=AiSuiteJobResponse)
def get_job_status(
    job_id: str,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> AiSuiteJobResponse:
    """Progress of one job; polled by the frontend while it runs."""
    job = container.ai_suite_service.get_job(workspace, job_id)
    return AiSuiteJobResponse.from_job(job)


@router.get("/jobs/{job_id}/results", response_model=AiSuiteResultsResponse)
def get_job_results(
    job_id: str,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> AiSuiteResultsResponse:
    """Every file the job produced; download them via ``/workspace/download``."""
    ai_suite_service = container.ai_suite_service
    job = ai_suite_service.get_job(workspace, job_id)

    return AiSuiteResultsResponse(
        job_id=job.job_id,
        status=job.status.value,
        results_directory=ai_suite_service.results_relative_directory(workspace, job),
        files=ai_suite_service.collect_result_files(workspace, job),
        error_message=job.error_message,
    )
