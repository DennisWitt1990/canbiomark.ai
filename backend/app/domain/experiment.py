"""Value objects for the cell-selection workflow (formerly "module 3")."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping


@dataclass(frozen=True)
class Experiment:
    """One single-cell experiment offered by the shared data catalogue."""

    experiment_id: int
    catalogue_file_name: str
    experiment_name: str
    tissue_name: str

    @property
    def display_label(self) -> str:
        return f"{self.tissue_name} – {self.experiment_name}"

    @property
    def dataset_suffix(self) -> str:
        """The trailing token of the catalogue file, e.g. ``liver_03.txt`` -> ``03``."""
        return self.catalogue_file_name.split("_")[-1].split(".")[0]

    def dataset_path(self, catalogue_directory: Path) -> Path:
        return catalogue_directory / f"combined_adata_{self.dataset_suffix}.h5ad"


ALL_CELL_TYPES_SENTINEL = "ALL"


@dataclass(frozen=True)
class CellTypeSelection:
    """Which cell types the user keeps, per experiment name."""

    selection_by_experiment: Mapping[str, List[str]]

    def experiment_names(self) -> List[str]:
        return list(self.selection_by_experiment.keys())

    def selects_every_cell_type(self, experiment_name: str) -> bool:
        return self.selection_by_experiment.get(experiment_name) == [
            ALL_CELL_TYPES_SENTINEL
        ]

    def cell_types_for(self, experiment_name: str) -> List[str]:
        return list(self.selection_by_experiment.get(experiment_name, []))

    def require_non_empty(self) -> None:
        from .errors import ValidationError

        if not self.selection_by_experiment:
            raise ValidationError("No cell types were selected.")
        for experiment_name, cell_types in self.selection_by_experiment.items():
            if not cell_types:
                raise ValidationError(
                    f"No cell type selected for experiment '{experiment_name}'."
                )

    @classmethod
    def from_mapping(cls, raw: Dict[str, List[str]]) -> "CellTypeSelection":
        return cls({str(key): [str(value) for value in values] for key, values in raw.items()})
