"""The cell selector: browse experiments, merge two of them, filter cell types."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from ...container import ServiceContainer
from ...domain.experiment import CellTypeSelection
from ...services.workspace_service import UserWorkspace
from ..dependencies import get_container, get_current_user, get_current_workspace
from ..schemas.cell_selection_schemas import (
    ExperimentResponse,
    SelectCellTypesRequest,
    FilterCellTypesRequest,
    FilterCellTypesResponse,
    MergeExperimentsRequest,
    MergeExperimentsResponse,
)

router = APIRouter(
    prefix="/cell-selection",
    tags=["cell selection"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/experiments", response_model=List[ExperimentResponse])
def list_experiments(
    container: ServiceContainer = Depends(get_container),
) -> List[ExperimentResponse]:
    """Every experiment offered by the shared data catalogue."""
    experiments = container.experiment_catalog_service.list_experiments()
    return [ExperimentResponse.from_experiment(item) for item in experiments]


@router.post("/merge", response_model=MergeExperimentsResponse)
def merge_experiments(
    merge_request: MergeExperimentsRequest,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> MergeExperimentsResponse:
    """Merge the two chosen experiments and report their cell types."""
    merge_result = container.cell_selection_service.merge_experiments(
        workspace, merge_request.experiment_ids
    )
    return MergeExperimentsResponse(
        merged_path=merge_result.merged_relative_path,
        cell_types_by_experiment=merge_result.cell_types_by_experiment,
    )


@router.post("/filter", response_model=FilterCellTypesResponse)
def filter_cell_types(
    filter_request: FilterCellTypesRequest,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> FilterCellTypesResponse:
    """Keep only the selected cell types and write the final dataset."""
    final_path = container.cell_selection_service.filter_selected_cell_types(
        workspace,
        filter_request.merged_path,
        CellTypeSelection.from_mapping(filter_request.selected_cell_types),
    )
    return FilterCellTypesResponse(final_path=final_path)


@router.post("/cell-types")
def list_cell_types(
    request: MergeExperimentsRequest,
    container: ServiceContainer = Depends(get_container),
):
    return {"cell_types_by_experiment": container.cell_selection_service.list_cell_types(request.experiment_ids)}


@router.post("/select", response_model=FilterCellTypesResponse)
def create_selected_dataset(
    request: SelectCellTypesRequest,
    workspace: UserWorkspace = Depends(get_current_workspace),
    container: ServiceContainer = Depends(get_container),
) -> FilterCellTypesResponse:
    path = container.cell_selection_service.create_selected_dataset(
        workspace, request.experiment_ids, CellTypeSelection.from_mapping(request.selected_cell_types)
    )
    return FilterCellTypesResponse(final_path=path)
