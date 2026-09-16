"""Choosing which ``obs`` column of an h5ad holds the cell type.

Every dataset spells this differently, and getting it wrong silently poisons
everything downstream: SimBu would simulate tissues out of mislabelled cells.
The rule inherited from the predecessor pipeline therefore holds here too --
**never guess silently**. The application proposes, a person confirms.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Column names that are known to carry a cell type, best first.
#
# Deliberately NOT in this list, although the predecessor pipeline had them:
#   * "Factor Value[single cell identifier]" and its ontology variant -- these
#     hold cell barcodes. In E-MTAB-2983 the values are "24", "5", "27", which
#     would yield 38 meaningless "cell types".
#   * "Sample Characteristic[sampling site]" -- that is a tissue, not a cell
#     type.
# Both would have produced a confidently wrong annotation.
KNOWN_CELL_TYPE_COLUMNS: Tuple[str, ...] = (
    "cell_type",
    "cell_type_ontology_term_id",
    "authors_cell_type_-_ontology_labels",
    "Factor Value[inferred cell type - ontology labels]",
    "Factor Value[inferred cell type - authors labels]",
    "Sample Characteristic[cell type]",
    "celltype",
    "CellType",
    "cell_ontology_class",
    "annotation",
)

# Substrings that make an unknown column plausible as a cell type.
CELL_TYPE_NAME_HINTS: Tuple[str, ...] = (
    "cell type",
    "cell_type",
    "celltype",
    "cluster",
    "annotation",
    "ontology label",
    "lineage",
    "phenotype",
)

# Substrings that rule a column out however plausible it otherwise looks.
DISQUALIFYING_NAME_HINTS: Tuple[str, ...] = (
    "identifier",
    "barcode",
    "ontology_term_id",
    "ontology term[",
    "individual",
    "donor",
    "patient",
    "sample id",
    "organism part",
    "sampling site",
)

# "<na>" and "nat" appear when a pandas nullable column is stringified during
# the 0.7.6 conversion; without them those cells would count as real labels.
VALUES_TREATED_AS_MISSING = frozenset(
    {
        "",
        "nan",
        "none",
        "na",
        "n/a",
        "null",
        "nat",
        "<na>",
        "unknown",
        "unassigned",
        "not applicable",
        "--",
    }
)

# A cell type column has repeated labels. These bounds reject both a constant
# column and a per-cell identifier.
MINIMUM_SENSIBLE_CATEGORY_COUNT = 2
MAXIMUM_SENSIBLE_CATEGORY_COUNT = 300
MAXIMUM_SENSIBLE_DISTINCT_FRACTION = 0.5


@dataclass(frozen=True)
class ColumnValueSummary:
    """What a column actually contains, enough to judge it by eye."""

    column_name: str
    total_cells: int
    distinct_value_count: int
    missing_cell_count: int
    most_frequent_values: List[Tuple[str, int]] = field(default_factory=list)
    example_values: List[str] = field(default_factory=list)

    @property
    def missing_fraction(self) -> float:
        if self.total_cells == 0:
            return 0.0
        return self.missing_cell_count / self.total_cells

    @property
    def distinct_fraction(self) -> float:
        if self.total_cells == 0:
            return 0.0
        return self.distinct_value_count / self.total_cells

    @property
    def looks_like_an_identifier(self) -> bool:
        """Nearly one distinct value per cell means barcodes, not cell types."""
        return (
            self.distinct_fraction > MAXIMUM_SENSIBLE_DISTINCT_FRACTION
            or self.distinct_value_count > MAXIMUM_SENSIBLE_CATEGORY_COUNT
        )

    @property
    def is_constant(self) -> bool:
        return self.distinct_value_count < MINIMUM_SENSIBLE_CATEGORY_COUNT


@dataclass(frozen=True)
class CellTypeColumnCandidate:
    """One ``obs`` column, scored and explained for the selection dialog."""

    summary: ColumnValueSummary
    score: float
    is_known_name: bool
    reasons: List[str] = field(default_factory=list)

    @property
    def column_name(self) -> str:
        return self.summary.column_name

    @property
    def is_usable(self) -> bool:
        """Whether the column can be accepted as a cell type annotation.

        A *constant* column stays usable on purpose. A dataset that contains a
        single cell type is perfectly legitimate -- one real CELLxGENE dataset
        has 637 cells that are all "vascular leptomeningeal cell" -- and its
        ``cell_type`` column is still the right one. It is flagged instead,
        because SimBu needs at least two types to mix.
        """
        return (
            not self.summary.looks_like_an_identifier
            and self.summary.missing_fraction < 1.0
        )

    @property
    def yields_a_single_cell_type(self) -> bool:
        """Usable, but SimBu cannot build a mixture out of one type."""
        return self.is_usable and self.summary.is_constant


class CellTypeColumnScorer:
    """Ranks ``obs`` columns by how likely they are to hold the cell type."""

    def score(self, summary: ColumnValueSummary) -> CellTypeColumnCandidate:
        reasons: List[str] = []
        score = 0.0
        normalized_name = summary.column_name.strip().lower()

        is_known_name = summary.column_name in KNOWN_CELL_TYPE_COLUMNS
        if is_known_name:
            # Earlier entries in the known list score higher.
            position = KNOWN_CELL_TYPE_COLUMNS.index(summary.column_name)
            score += 100.0 - position
            reasons.append("A known cell type column name.")
        elif any(hint in normalized_name for hint in CELL_TYPE_NAME_HINTS):
            score += 40.0
            reasons.append("The column name suggests a cell type.")

        if any(hint in normalized_name for hint in DISQUALIFYING_NAME_HINTS):
            score -= 80.0
            reasons.append(
                "The name suggests an identifier or a sample property, not a cell type."
            )

        if summary.is_constant:
            # Smaller than the known-name bonus on purpose: a constant
            # `cell_type` is still the cell type column, it just describes a
            # single-cell-type dataset.
            score -= 25.0
            reasons.append(
                "Every cell carries the same value, so this dataset holds a "
                "single cell type. SimBu needs at least two to mix."
            )
        elif summary.looks_like_an_identifier:
            score -= 100.0
            reasons.append(
                f"{summary.distinct_value_count} distinct values for "
                f"{summary.total_cells} cells looks like a per-cell identifier."
            )
        else:
            score += 20.0
            reasons.append(
                f"{summary.distinct_value_count} distinct labels across "
                f"{summary.total_cells} cells."
            )

        if summary.missing_fraction > 0.5:
            score -= 30.0
            reasons.append(
                f"{summary.missing_fraction:.0%} of the cells have no value."
            )
        elif summary.missing_fraction > 0.0:
            score -= 5.0
            reasons.append(
                f"{summary.missing_fraction:.0%} of the cells have no value."
            )

        return CellTypeColumnCandidate(
            summary=summary,
            score=score,
            is_known_name=is_known_name,
            reasons=reasons,
        )

    def rank(self, summaries: List[ColumnValueSummary]) -> List[CellTypeColumnCandidate]:
        """Score every column and return them best first.

        A column with a known cell type name is always ranked above one without,
        whatever the numeric score. Otherwise an unrelated column can win a tie
        on ordering alone -- observed on a real dataset where "Age at death"
        outranked a constant but correct ``cell_type``.
        """
        candidates = [self.score(summary) for summary in summaries]
        candidates.sort(
            key=lambda candidate: (
                candidate.is_known_name and candidate.is_usable,
                candidate.score,
            ),
            reverse=True,
        )
        return candidates

    @staticmethod
    def recommended(
        candidates: List[CellTypeColumnCandidate],
    ) -> Optional[CellTypeColumnCandidate]:
        """The best usable candidate, or ``None`` when nothing is plausible."""
        for candidate in candidates:
            if candidate.is_known_name and candidate.is_usable:
                return candidate
        for candidate in candidates:
            if candidate.is_usable and candidate.score > 0:
                return candidate
        return None
