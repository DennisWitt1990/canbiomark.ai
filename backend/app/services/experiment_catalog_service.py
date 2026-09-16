"""Reads the shared catalogue of available single-cell experiments.

The catalogue is a set of ``*.txt`` files in the shared input directory; each
line holds ``<experiment name>;<tissue name>``.  The matching expression matrix
lives next to it as ``combined_adata_<suffix>.h5ad``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from ..domain.errors import ResourceNotFoundError
from ..domain.experiment import Experiment

_logger = logging.getLogger(__name__)

_CATALOGUE_ENCODINGS = ("utf-8", "cp1252")


class ExperimentCatalogService:
    """Parses the catalogue files and resolves experiments to datasets."""

    def __init__(self, catalogue_directory: Path) -> None:
        self._catalogue_directory = Path(catalogue_directory)

    @property
    def catalogue_directory(self) -> Path:
        return self._catalogue_directory

    def list_experiments(self) -> List[Experiment]:
        """All experiments, de-duplicated and sorted by tissue then experiment."""
        unique_entries = sorted(
            set(self._read_catalogue_entries()), key=lambda entry: (entry[2], entry[1])
        )
        return [
            Experiment(
                experiment_id=index,
                catalogue_file_name=catalogue_file_name,
                experiment_name=experiment_name,
                tissue_name=tissue_name,
            )
            for index, (catalogue_file_name, experiment_name, tissue_name) in enumerate(
                unique_entries
            )
        ]

    def get_by_ids(self, experiment_ids: Sequence[int]) -> List[Experiment]:
        experiments_by_id: Dict[int, Experiment] = {
            experiment.experiment_id: experiment
            for experiment in self.list_experiments()
        }
        selected: List[Experiment] = []
        for experiment_id in experiment_ids:
            experiment = experiments_by_id.get(int(experiment_id))
            if experiment is None:
                raise ResourceNotFoundError(f"Unknown experiment id: {experiment_id}")
            selected.append(experiment)
        return selected

    def dataset_path_for(self, experiment: Experiment) -> Path:
        dataset_path = experiment.dataset_path(self._catalogue_directory)
        if not dataset_path.exists():
            raise ResourceNotFoundError(
                f"The dataset file '{dataset_path.name}' is missing on the server."
            )
        return dataset_path

    # -- parsing -----------------------------------------------------------

    def _read_catalogue_entries(self) -> List[Tuple[str, str, str]]:
        entries: List[Tuple[str, str, str]] = []

        if not self._catalogue_directory.exists():
            _logger.warning(
                "Catalogue directory %s does not exist.", self._catalogue_directory
            )
            return entries

        for catalogue_file in sorted(self._catalogue_directory.glob("*.txt")):
            entries.extend(self._read_single_catalogue_file(catalogue_file))
        return entries

    @staticmethod
    def _read_single_catalogue_file(catalogue_file: Path) -> List[Tuple[str, str, str]]:
        """Read one catalogue file, tolerating Windows-1252 encoded degree signs."""
        for encoding in _CATALOGUE_ENCODINGS:
            try:
                raw_text = catalogue_file.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

            entries: List[Tuple[str, str, str]] = []
            for line in raw_text.splitlines():
                columns = [column.strip() for column in line.split(";")]
                if len(columns) == 2 and all(columns):
                    experiment_name, tissue_name = columns
                    entries.append((catalogue_file.name, experiment_name, tissue_name))
            return entries

        _logger.error("Could not decode catalogue file %s.", catalogue_file)
        return []
