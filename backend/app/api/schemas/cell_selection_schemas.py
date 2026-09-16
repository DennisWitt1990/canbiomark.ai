"""Wire format of the cell selector."""
from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field

from ...domain.experiment import Experiment


class ExperimentResponse(BaseModel):
    """One selectable experiment."""

    experiment_id: int
    experiment_name: str
    tissue_name: str
    catalogue_file_name: str
    display_label: str

    @classmethod
    def from_experiment(cls, experiment: Experiment) -> "ExperimentResponse":
        return cls(
            experiment_id=experiment.experiment_id,
            experiment_name=experiment.experiment_name,
            tissue_name=experiment.tissue_name,
            catalogue_file_name=experiment.catalogue_file_name,
            display_label=experiment.display_label,
        )


class MergeExperimentsRequest(BaseModel):
    """Exactly two experiment ids to merge."""

    experiment_ids: List[int] = Field(..., min_length=2, max_length=2)


class MergeExperimentsResponse(BaseModel):
    """The merged dataset plus the cell types found per experiment."""

    merged_path: str
    cell_types_by_experiment: Dict[str, List[str]]


class FilterCellTypesRequest(BaseModel):
    """Which cell types to keep, per experiment."""

    merged_path: str = Field(..., min_length=1)
    selected_cell_types: Dict[str, List[str]]


class FilterCellTypesResponse(BaseModel):
    """The final, SimBu-ready dataset."""

    final_path: str


class SelectCellTypesRequest(MergeExperimentsRequest):
    """Experiments and cell types chosen before creating the dataset."""

    selected_cell_types: Dict[str, List[str]]
