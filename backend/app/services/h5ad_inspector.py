"""Reads the ``obs`` metadata of an h5ad without loading the matrix.

A downloaded dataset can be several gigabytes, and the user only needs to see
the observation columns to pick the cell type one. Using ``h5py`` directly
keeps that to a metadata read of a few megabytes instead of a full
``scanpy.read_h5ad``.

Both storage layouts are handled: a plain array per column, and the categorical
form that anndata writes as a group of ``categories`` plus integer ``codes``.
"""
from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import List, Optional

from ..domain.cell_type_column import (
    CellTypeColumnCandidate,
    CellTypeColumnScorer,
    ColumnValueSummary,
    VALUES_TREATED_AS_MISSING,
)
from ..domain.errors import ResourceNotFoundError, ValidationError

_logger = logging.getLogger(__name__)

MOST_FREQUENT_VALUES_SHOWN = 5
EXAMPLE_VALUES_SHOWN = 3
# Columns with more distinct values than this are summarised but never ranked
# highly; reading them fully is still cheap because obs is metadata only.
MAXIMUM_COLUMNS_INSPECTED = 200


class H5adInspector:
    """Summarises the observation columns of an h5ad file."""

    def __init__(self, scorer: Optional[CellTypeColumnScorer] = None) -> None:
        self._scorer = scorer or CellTypeColumnScorer()

    # -- public API --------------------------------------------------------

    def rank_cell_type_columns(self, dataset_path: Path) -> List[CellTypeColumnCandidate]:
        """Every observation column, scored and sorted best first."""
        summaries = self.summarise_observation_columns(dataset_path)
        return self._scorer.rank(summaries)

    def summarise_observation_columns(
        self, dataset_path: Path
    ) -> List[ColumnValueSummary]:
        import h5py

        dataset_path = Path(dataset_path)
        if not dataset_path.is_file():
            raise ResourceNotFoundError(f"'{dataset_path.name}' does not exist.")

        summaries: List[ColumnValueSummary] = []
        try:
            with h5py.File(dataset_path, "r") as h5_file:
                if "obs" not in h5_file:
                    raise ValidationError(
                        f"'{dataset_path.name}' has no 'obs' group and is not a "
                        f"usable AnnData file."
                    )
                observation_group = h5_file["obs"]
                column_names = [
                    name
                    for name in observation_group.keys()
                    if not name.startswith("_")
                ][:MAXIMUM_COLUMNS_INSPECTED]

                for column_name in column_names:
                    summary = self._summarise_column(observation_group, column_name)
                    if summary is not None:
                        summaries.append(summary)
        except OSError as error:
            raise ValidationError(
                f"'{dataset_path.name}' could not be read as an HDF5 file: {error}"
            ) from error

        if not summaries:
            raise ValidationError(
                f"'{dataset_path.name}' has no readable observation columns."
            )
        return summaries

    def read_dataset_shape(self, dataset_path: Path) -> tuple[int, int]:
        """``(cells, genes)`` read from the metadata, without loading X."""
        import h5py

        with h5py.File(Path(dataset_path), "r") as h5_file:
            cell_count = self._count_rows(h5_file["obs"]) if "obs" in h5_file else 0
            gene_count = self._count_rows(h5_file["var"]) if "var" in h5_file else 0
        return cell_count, gene_count

    # -- internals ---------------------------------------------------------

    def _summarise_column(
        self, observation_group, column_name: str
    ) -> Optional[ColumnValueSummary]:
        try:
            values = self._read_column_values(observation_group, column_name)
        except Exception:  # noqa: BLE001 - one odd column must not stop the rest
            _logger.debug("Could not read obs column %r.", column_name, exc_info=True)
            return None

        if values is None:
            return None

        missing_count = sum(
            1 for value in values if value.strip().lower() in VALUES_TREATED_AS_MISSING
        )
        present_values = [
            value
            for value in values
            if value.strip().lower() not in VALUES_TREATED_AS_MISSING
        ]
        value_counts = Counter(present_values)

        return ColumnValueSummary(
            column_name=column_name,
            total_cells=len(values),
            distinct_value_count=len(value_counts),
            missing_cell_count=missing_count,
            most_frequent_values=value_counts.most_common(MOST_FREQUENT_VALUES_SHOWN),
            # Show values that actually exist: the first rows of a real dataset
            # are frequently blank, which makes a raw head() useless here.
            example_values=[value for value, _ in value_counts.most_common(EXAMPLE_VALUES_SHOWN)],
        )

    @staticmethod
    def _read_column_values(observation_group, column_name: str) -> Optional[List[str]]:
        """Return one column as a list of strings, whatever its storage form."""
        import h5py
        import numpy

        node = observation_group[column_name]

        def decode(raw_value) -> str:
            if isinstance(raw_value, bytes):
                return raw_value.decode("utf-8", errors="replace")
            return str(raw_value)

        if isinstance(node, h5py.Group):
            # anndata's categorical layout: categories + integer codes.
            if "categories" not in node or "codes" not in node:
                return None
            categories = [decode(value) for value in node["categories"][:]]
            codes = node["codes"][:]
            return [
                categories[code] if 0 <= code < len(categories) else ""
                for code in codes
            ]

        raw_values = node[:]
        if raw_values.dtype.kind in {"f", "i", "u", "b"}:
            return [
                "" if isinstance(value, float) and numpy.isnan(value) else decode(value)
                for value in raw_values
            ]
        return [decode(value) for value in raw_values]

    @staticmethod
    def _count_rows(group) -> int:
        import h5py

        index_name = group.attrs.get("_index")
        if isinstance(index_name, bytes):
            index_name = index_name.decode()
        if index_name and index_name in group:
            return int(group[index_name].shape[0])

        for node in group.values():
            if isinstance(node, h5py.Dataset):
                return int(node.shape[0])
            if isinstance(node, h5py.Group) and "codes" in node:
                return int(node["codes"].shape[0])
        return 0
