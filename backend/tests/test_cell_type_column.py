"""The cell type column must never be guessed wrongly in silence.

These tests pin the behaviour that matters: an identifier column is refused, a
constant column is refused, and when nothing is plausible the scorer recommends
nothing rather than picking the least bad option.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.cell_type_column import (
    CellTypeColumnScorer,
    ColumnValueSummary,
    KNOWN_CELL_TYPE_COLUMNS,
)
from app.services.h5ad_inspector import H5adInspector


def make_summary(
    column_name: str,
    *,
    total_cells: int = 1000,
    distinct: int = 12,
    missing: int = 0,
) -> ColumnValueSummary:
    return ColumnValueSummary(
        column_name=column_name,
        total_cells=total_cells,
        distinct_value_count=distinct,
        missing_cell_count=missing,
        most_frequent_values=[(f"label{i}", 10) for i in range(min(distinct, 5))],
        example_values=[f"label{i}" for i in range(min(distinct, 3))],
    )


# --- the candidate list itself ---------------------------------------------


@pytest.mark.parametrize(
    "forbidden_name",
    [
        "Factor Value[single cell identifier]",
        "Factor Value Ontology Term[single cell identifier]",
        "Sample Characteristic[sampling site]",
    ],
)
def test_identifier_and_site_columns_are_not_known_cell_type_columns(
    forbidden_name: str,
) -> None:
    """These were in the predecessor's candidate list and are not cell types.

    ``Factor Value[single cell identifier]`` holds cell barcodes -- in
    E-MTAB-2983 its values are "24", "5", "27" -- and ``sampling site`` is a
    tissue. Accepting either produces a confidently wrong annotation.
    """
    assert forbidden_name not in KNOWN_CELL_TYPE_COLUMNS


def test_cell_type_is_the_highest_scoring_known_name() -> None:
    scorer = CellTypeColumnScorer()
    ranked = scorer.rank(
        [
            make_summary("donor_id", distinct=6),
            make_summary("cell_type", distinct=15),
            make_summary("tissue", distinct=1),
        ]
    )
    assert ranked[0].column_name == "cell_type"


# --- rejection rules --------------------------------------------------------


def test_a_per_cell_identifier_is_rejected() -> None:
    """Nearly one distinct value per cell means barcodes, not cell types."""
    candidate = CellTypeColumnScorer().score(
        make_summary("barcode", total_cells=1000, distinct=990)
    )
    assert not candidate.is_usable
    assert candidate.summary.looks_like_an_identifier


def test_a_constant_column_is_flagged_but_not_rejected() -> None:
    """A single-cell-type dataset is legitimate; the column is still valid.

    Observed on a real CELLxGENE dataset whose 637 cells are all "vascular
    leptomeningeal cell". Rejecting its `cell_type` column as unusable pushed
    the recommendation onto an unrelated column instead.
    """
    candidate = CellTypeColumnScorer().score(make_summary("tissue", distinct=1))

    assert candidate.summary.is_constant
    assert candidate.is_usable
    assert candidate.yields_a_single_cell_type
    # It is still penalised, so anything richer outranks it.
    assert candidate.score < 0


def test_a_constant_but_known_cell_type_column_is_still_recommended() -> None:
    """The regression for the "Age at death" incident.

    A known cell type name must never be outranked by an unrelated column, even
    when the known one is constant and therefore penalised.
    """
    scorer = CellTypeColumnScorer()
    ranked = scorer.rank(
        [
            make_summary("Age at death", distinct=3),
            make_summary("Supertype", distinct=2),
            make_summary("sex", distinct=2),
            make_summary("cell_type", distinct=1),
        ]
    )

    assert ranked[0].column_name == "cell_type"
    recommended = CellTypeColumnScorer.recommended(ranked)
    assert recommended is not None
    assert recommended.column_name == "cell_type"
    assert recommended.yields_a_single_cell_type
    assert any("single cell type" in reason for reason in recommended.reasons)


def test_a_name_that_suggests_an_identifier_is_penalised() -> None:
    scorer = CellTypeColumnScorer()
    identifier_like = scorer.score(make_summary("single cell identifier", distinct=38))
    plain = scorer.score(make_summary("annotation", distinct=38))
    assert identifier_like.score < plain.score


def test_nothing_is_recommended_when_no_column_is_plausible() -> None:
    """The E-MTAB-2983 case: the dataset simply has no cell type annotation."""
    scorer = CellTypeColumnScorer()
    ranked = scorer.rank(
        [
            make_summary("Sample Characteristic[organism part]", distinct=1),
            make_summary("Sample Characteristic[disease]", distinct=1),
            make_summary("Factor Value[single cell identifier]", total_cells=60, distinct=38),
        ]
    )
    assert CellTypeColumnScorer.recommended(ranked) is None


def test_a_column_with_many_missing_values_is_penalised_but_still_usable() -> None:
    """E-HCAD-10 has 21.9 % empty labels and is still the right column."""
    scorer = CellTypeColumnScorer()
    complete = scorer.score(make_summary("cell_type", distinct=29, missing=0))
    sparse_column = scorer.score(make_summary("cell_type", distinct=29, missing=219))
    assert sparse_column.score < complete.score
    assert sparse_column.is_usable


def test_both_valid_columns_of_one_dataset_stay_usable() -> None:
    """E-HCAD-10 offers author labels and ontology labels; both are legitimate."""
    scorer = CellTypeColumnScorer()
    ranked = scorer.rank(
        [
            make_summary(
                "Factor Value[inferred cell type - authors labels]",
                total_cells=31711, distinct=44, missing=6936,
            ),
            make_summary(
                "Factor Value[inferred cell type - ontology labels]",
                total_cells=31711, distinct=29, missing=6936,
            ),
        ]
    )
    assert all(candidate.is_usable for candidate in ranked)
    # The choice between them is the user's, so they must score close together.
    assert abs(ranked[0].score - ranked[1].score) < 10


# --- the inspector ----------------------------------------------------------


def test_reading_a_file_that_is_not_hdf5_is_reported_clearly(tmp_path: Path) -> None:
    from app.domain.errors import ValidationError

    broken_file = tmp_path / "not_really.h5ad"
    broken_file.write_text("this is not an HDF5 file")

    with pytest.raises(ValidationError, match="HDF5"):
        H5adInspector().summarise_observation_columns(broken_file)


def test_reading_a_missing_file_is_reported_clearly(tmp_path: Path) -> None:
    from app.domain.errors import ResourceNotFoundError

    with pytest.raises(ResourceNotFoundError):
        H5adInspector().summarise_observation_columns(tmp_path / "absent.h5ad")
