"""Finding datasets online and importing them into the shared catalogue.

Administrator only: an import writes into the shared data directory that every
user reads from, and the files run to several gigabytes. Researchers browse the
catalogue through the cell selector instead.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from ...container import ServiceContainer
from ...domain.user_account import UserAccount
from ..dependencies import get_container, get_current_administrator
from ..schemas.authentication_schemas import SimpleAcknowledgement
from ..schemas.dataset_import_schemas import (
    CellTypeDecisionResponse,
    ColumnCandidateResponse,
    ConfirmCellTypeColumnRequest,
    DatasetImportJobResponse,
    DatasetSearchRequest,
    RemoteDatasetResponse,
    StartImportRequest,
)

router = APIRouter(
    prefix="/dataset-import",
    tags=["dataset import"],
    dependencies=[Depends(get_current_administrator)],
)


@router.post("/search", response_model=List[RemoteDatasetResponse])
def search_datasets(
    search_request: DatasetSearchRequest,
    container: ServiceContainer = Depends(get_container),
) -> List[RemoteDatasetResponse]:
    """Search CELLxGENE Discover, or look up one EBI BioStudies accession."""
    datasets = container.dataset_search_service.search(
        source=search_request.parsed_source(),
        query=search_request.query,
        organism=search_request.organism,
        limit=search_request.limit,
    )
    return [RemoteDatasetResponse.from_dataset(dataset) for dataset in datasets]


@router.post("/jobs", response_model=DatasetImportJobResponse, status_code=202)
def start_import(
    start_request: StartImportRequest,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> DatasetImportJobResponse:
    """Download a dataset; the import then pauses for the cell type column."""
    job = container.dataset_import_service.start_import(
        administrator_user_id=administrator.user_id,
        remote_dataset=start_request.dataset.to_dataset(),
        catalogue_name=start_request.catalogue_name,
    )
    return DatasetImportJobResponse.from_job(job)


@router.get("/jobs", response_model=List[DatasetImportJobResponse])
def list_imports(
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> List[DatasetImportJobResponse]:
    """Every import started by the signed-in administrator, newest first."""
    jobs = container.dataset_import_service.list_jobs(administrator.user_id)
    return [DatasetImportJobResponse.from_job(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=DatasetImportJobResponse)
def get_import(
    job_id: str,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> DatasetImportJobResponse:
    """Progress of one import; polled while it downloads and converts."""
    job = container.dataset_import_service.get_job(job_id, administrator.user_id)
    return DatasetImportJobResponse.from_job(job)


@router.get("/jobs/{job_id}/cell-type-column", response_model=CellTypeDecisionResponse)
def get_cell_type_candidates(
    job_id: str,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> CellTypeDecisionResponse:
    """The observation columns, scored, with what each one actually contains.

    The recommendation may be ``null``: when no column is plausibly a cell type
    the importer says so rather than picking one, because a wrong cell type
    produces a dataset that simulates fine and means nothing.
    """
    decision = container.dataset_import_service.get_cell_type_decision(
        job_id, administrator.user_id
    )
    return CellTypeDecisionResponse(
        job_id=decision.job_id,
        dataset_title=decision.dataset_title,
        recommended_column=decision.recommended_column,
        candidates=[
            ColumnCandidateResponse.from_candidate(candidate)
            for candidate in decision.candidates
        ],
    )


@router.post("/jobs/{job_id}/cell-type-column", response_model=DatasetImportJobResponse)
def confirm_cell_type_column(
    job_id: str,
    confirm_request: ConfirmCellTypeColumnRequest,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> DatasetImportJobResponse:
    """Accept the chosen column and resume the conversion."""
    job = container.dataset_import_service.confirm_cell_type_column(
        job_id, administrator.user_id, confirm_request.column_name
    )
    return DatasetImportJobResponse.from_job(job)


@router.delete("/jobs/{job_id}", response_model=SimpleAcknowledgement)
def cancel_import(
    job_id: str,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> SimpleAcknowledgement:
    """Cancel an import and discard whatever it has downloaded so far."""
    container.dataset_import_service.cancel(job_id, administrator.user_id)
    return SimpleAcknowledgement(message="The import was cancelled.")
