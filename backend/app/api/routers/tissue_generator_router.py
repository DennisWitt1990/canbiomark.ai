"""Synthetic tissue generation with SimBu: single runs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from ...container import ServiceContainer
from ...domain.simbu import SimBuParameters
from ...services.workspace_service import UserWorkspace
from ..dependencies import get_container, get_current_user, get_current_workspace
from ..schemas.tissue_schemas import (
    RunSimulationRequest,
    RunSimulationResponse,
    TissueUploadResponse,
)

router = APIRouter(
    prefix="/tissue-generator",
    tags=["tissue generator"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/upload", response_model=TissueUploadResponse)
def upload_dataset(
    file: UploadFile = File(..., description="A single-cell dataset (.h5ad)."),
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> TissueUploadResponse:
    """Store a ``.h5ad`` in the caller's upload folder.

    The sample name is derived from the file name, so the browser cannot choose
    a storage location.
    """
    original_file_name = file.filename or ""
    stored_path = container.tissue_generator_service.store_uploaded_dataset(
        workspace, original_file_name, file.file
    )
    return TissueUploadResponse(
        stored_path=stored_path,
        sample_base_name=SimBuParameters.sanitize_sample_name(original_file_name),
    )


@router.post("/run", response_model=RunSimulationResponse)
def run_simulation(
    run_request: RunSimulationRequest,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> RunSimulationResponse:
    """Run one SimBu simulation synchronously.

    A failed R run is reported as ``succeeded = false`` with its logs attached,
    rather than as an HTTP error, so the frontend can always show stdout/stderr.
    """
    parameters = SimBuParameters.create(
        immune_cell_fraction=run_request.immune_cell_fraction,
        sample_count=run_request.sample_count,
        sample_base_name=run_request.sample_base_name,
    )
    result = container.tissue_generator_service.run_single_simulation(
        workspace, parameters
    )
    return RunSimulationResponse.from_result(result)
