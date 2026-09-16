"""The cell-selection workflow (formerly "module 3").

Two experiments are merged into one AnnData object; the user then picks the
cell types to keep and the service writes the final, SimBu-ready dataset into
the user's workspace.

The heavy scientific libraries are imported lazily inside the methods so that
importing this module (for example during a unit test of the API layer) does
not pull in scanpy.
"""
from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

from ..domain.errors import ValidationError
from ..domain.experiment import CellTypeSelection, Experiment
from .experiment_catalog_service import ExperimentCatalogService
from .workspace_service import UserWorkspace

_logger = logging.getLogger(__name__)

MERGED_DATASET_FILE_NAME = "merged_experiments.h5ad"
FILTERED_DATASET_FILE_NAME = "final_mod_daten.h5ad"

REQUIRED_EXPERIMENT_COUNT = 2

_OBSERVATION_EXPERIMENT_COLUMN = "file_name"
_OBSERVATION_CELL_TYPE_COLUMN = "cell_type"
_OBSERVATION_SET_COLUMN = "set"
_OBSERVATION_DONOR_COLUMN = "Sample.Characteristic.individual"


@dataclass(frozen=True)
class MergeResult:
    """Outcome of merging two experiments."""

    merged_relative_path: str
    cell_types_by_experiment: Dict[str, List[str]]


class CellSelectionService:
    """Merges experiments and filters them down to the selected cell types."""

    def __init__(self, experiment_catalog: ExperimentCatalogService) -> None:
        self._experiment_catalog = experiment_catalog

    def list_cell_types(self, experiment_ids: Sequence[int]) -> Dict[str, List[str]]:
        """Read observation metadata before loading or merging expression matrices."""
        import scanpy

        if len(experiment_ids) != REQUIRED_EXPERIMENT_COUNT or len(set(experiment_ids)) != REQUIRED_EXPERIMENT_COUNT:
            raise ValidationError("Select exactly two different experiments.")
        experiments = self._experiment_catalog.get_by_ids(experiment_ids)
        if len({item.experiment_name for item in experiments}) != len(experiments):
            raise ValidationError("The selected catalogue entries must have different experiment names.")
        result = {}
        for experiment in experiments:
            dataset = scanpy.read_h5ad(self._experiment_catalog.dataset_path_for(experiment), backed="r")
            try:
                required = {_OBSERVATION_EXPERIMENT_COLUMN, _OBSERVATION_CELL_TYPE_COLUMN}
                if not required.issubset(dataset.obs.columns):
                    raise ValidationError("The dataset needs file_name and cell_type annotations.")
                cells = dataset.obs.loc[dataset.obs[_OBSERVATION_EXPERIMENT_COLUMN] == experiment.experiment_name, _OBSERVATION_CELL_TYPE_COLUMN]
                types = sorted(cells.dropna().astype(str).unique().tolist())
                if not types:
                    raise ValidationError(f"No annotated cells found for '{experiment.experiment_name}'.")
                result[experiment.experiment_name] = types
            finally:
                dataset.file.close()
        return result

    def create_selected_dataset(self, workspace: UserWorkspace, experiment_ids: Sequence[int], selection: CellTypeSelection) -> str:
        """Select cells within each experiment, then merge the selected subsets."""
        import numpy
        import scanpy

        selection.require_non_empty()
        available = self.list_cell_types(experiment_ids)
        if set(selection.experiment_names()) != set(available):
            raise ValidationError("Choose cell types for each selected experiment.")
        for name, types in available.items():
            if not selection.selects_every_cell_type(name) and not set(selection.cell_types_for(name)).issubset(types):
                raise ValidationError(f"Unknown cell type selected for '{name}'.")
        subsets = []
        for experiment in self._experiment_catalog.get_by_ids(experiment_ids):
            subset = self._read_experiment_subset(scanpy, self._experiment_catalog.dataset_path_for(experiment), experiment)
            if not selection.selects_every_cell_type(experiment.experiment_name):
                subset = subset[subset.obs[_OBSERVATION_CELL_TYPE_COLUMN].isin(selection.cell_types_for(experiment.experiment_name)), :].copy()
            subsets.append(subset)
        dataset = scanpy.concat(subsets, join="outer")
        dataset.obs[_OBSERVATION_SET_COLUMN] = dataset.obs[_OBSERVATION_EXPERIMENT_COLUMN].astype("category").cat.codes.add(1).astype(str)
        self._normalize_observations(numpy, dataset)
        final_path = workspace.cell_selection_directory / FILTERED_DATASET_FILE_NAME
        dataset.write_h5ad(final_path)
        return workspace.to_relative_path(final_path)

    def merge_experiments(
        self, workspace: UserWorkspace, experiment_ids: Sequence[int]
    ) -> MergeResult:
        """Concatenate the chosen experiments and report their cell types."""
        if len(experiment_ids) != REQUIRED_EXPERIMENT_COUNT:
            raise ValidationError(
                f"Exactly {REQUIRED_EXPERIMENT_COUNT} experiments must be selected."
            )
        if len(set(experiment_ids)) != len(experiment_ids):
            raise ValidationError("The same experiment was selected twice.")

        import scanpy

        selected_experiments = self._experiment_catalog.get_by_ids(experiment_ids)

        subsets = []
        cell_types_by_experiment: Dict[str, List[str]] = {}

        for experiment in selected_experiments:
            dataset_path = self._experiment_catalog.dataset_path_for(experiment)
            subset = self._read_experiment_subset(scanpy, dataset_path, experiment)
            subsets.append(subset)
            cell_types_by_experiment[experiment.experiment_name] = sorted(
                subset.obs[_OBSERVATION_CELL_TYPE_COLUMN].astype(str).unique().tolist()
            )

        merged_dataset = scanpy.concat(subsets, join="outer")
        merged_dataset.obs[_OBSERVATION_SET_COLUMN] = (
            merged_dataset.obs[_OBSERVATION_EXPERIMENT_COLUMN]
            .astype("category")
            .cat.codes.add(1)
            .astype(str)
        )

        merged_path = workspace.cell_selection_directory / MERGED_DATASET_FILE_NAME
        merged_dataset.write_h5ad(merged_path)

        del merged_dataset, subsets
        gc.collect()

        return MergeResult(
            merged_relative_path=workspace.to_relative_path(merged_path),
            cell_types_by_experiment=cell_types_by_experiment,
        )

    def filter_selected_cell_types(
        self,
        workspace: UserWorkspace,
        merged_relative_path: str,
        selection: CellTypeSelection,
    ) -> str:
        """Keep only the selected cell types and write the final dataset."""
        selection.require_non_empty()

        import numpy
        import pandas
        import scanpy

        merged_path = workspace.resolve(merged_relative_path)
        dataset = scanpy.read_h5ad(merged_path)

        keep_mask = self._build_keep_mask(pandas, dataset, selection)
        if not bool(keep_mask.any()):
            raise ValidationError(
                "The selection does not match any cell in the merged dataset."
            )
        dataset = dataset[keep_mask, :].copy()
        del keep_mask
        gc.collect()

        self._normalize_observations(numpy, dataset)

        filtered_path = workspace.cell_selection_directory / FILTERED_DATASET_FILE_NAME
        dataset.write_h5ad(filtered_path)

        del dataset
        gc.collect()

        return workspace.to_relative_path(filtered_path)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _read_experiment_subset(scanpy_module, dataset_path: Path, experiment: Experiment):
        """Load one h5ad and keep only the rows belonging to ``experiment``."""
        full_dataset = scanpy_module.read_h5ad(dataset_path)
        subset = full_dataset[
            full_dataset.obs[_OBSERVATION_EXPERIMENT_COLUMN]
            == experiment.experiment_name,
            :,
        ].copy()

        del full_dataset
        gc.collect()

        if subset.n_obs == 0:
            raise ValidationError(
                f"Experiment '{experiment.experiment_name}' contains no cells in "
                f"'{dataset_path.name}'."
            )
        return subset

    @staticmethod
    def _build_keep_mask(pandas_module, dataset, selection: CellTypeSelection):
        """One boolean column per experiment, OR-ed together."""
        per_experiment_masks = []
        for experiment_name in selection.experiment_names():
            belongs_to_experiment = (
                dataset.obs[_OBSERVATION_EXPERIMENT_COLUMN] == experiment_name
            )
            if selection.selects_every_cell_type(experiment_name):
                per_experiment_masks.append(belongs_to_experiment)
            else:
                per_experiment_masks.append(
                    belongs_to_experiment
                    & dataset.obs[_OBSERVATION_CELL_TYPE_COLUMN].isin(
                        selection.cell_types_for(experiment_name)
                    )
                )
        return pandas_module.concat(per_experiment_masks, axis=1).any(axis=1)

    @staticmethod
    def _normalize_observations(numpy_module, dataset) -> None:
        """Reduce the metadata to the columns the SimBu R script expects."""
        dataset.obs = dataset.obs[
            [
                _OBSERVATION_CELL_TYPE_COLUMN,
                _OBSERVATION_EXPERIMENT_COLUMN,
                _OBSERVATION_SET_COLUMN,
            ]
        ].astype(str)
        dataset.obs.insert(
            0, "CellNr", numpy_module.arange(1, len(dataset.obs) + 1)
        )
        # Both experiments are modelled as the same synthetic donor, because
        # SimBu simulates one tissue from the combined cell pool.
        dataset.obs[_OBSERVATION_DONOR_COLUMN] = dataset.obs[
            _OBSERVATION_SET_COLUMN
        ].replace({"1": "donor1", "2": "donor1"})
