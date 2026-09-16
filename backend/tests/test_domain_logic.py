"""Unit tests of the domain objects and parsers."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.errors import PasswordPolicyError, ValidationError
from app.domain.experiment import CellTypeSelection, Experiment
from app.domain.simbu import SimBuParameters, SimBuRunResult
from app.security.password_hasher import PasswordHasher
from app.security.password_policy import PasswordPolicy
from app.services.batch_definition_parser import BatchDefinitionParser
from app.services.classification_metrics import ConfusionMatrix
from app.services.experiment_catalog_service import ExperimentCatalogService

# --- password handling -----------------------------------------------------


def test_the_same_password_produces_different_hashes() -> None:
    hasher = PasswordHasher(iterations=10_000)

    first = hasher.hash_password("correct horse 1")
    second = hasher.hash_password("correct horse 1")

    assert first.hash_hex != second.hash_hex  # each hash has its own salt
    assert hasher.verify_password("correct horse 1", first)
    assert hasher.verify_password("correct horse 1", second)
    assert not hasher.verify_password("wrong horse 1", first)


def test_a_raised_cost_factor_marks_old_hashes_for_rehashing() -> None:
    old_hash = PasswordHasher(iterations=10_000).hash_password("password 123")

    assert PasswordHasher(iterations=20_000).needs_rehash(old_hash)
    assert not PasswordHasher(iterations=10_000).needs_rehash(old_hash)


@pytest.mark.parametrize(
    "weak_password",
    ["short1", "no-digits-here", "1234567890", " leadingspace1", "trailingspace1 "],
)
def test_weak_passwords_are_refused(weak_password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        PasswordPolicy(minimum_length=10).validate(weak_password)


def test_generated_passwords_satisfy_the_policy() -> None:
    policy = PasswordPolicy(minimum_length=12)
    for _ in range(20):
        policy.validate(policy.generate())


# --- SimBu parameters ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [(20, 0.2), (0.2, 0.2), (99, 0.99), (150, 0.99), (-5, 0.0), (0, 0.0)],
)
def test_fractions_accept_percentages_and_ratios(raw_value, expected) -> None:
    assert SimBuParameters.normalize_fraction(raw_value) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("final_mod_daten.h5ad", "final_mod_daten"),
        ("/etc/passwd", "passwd"),
        ("subdir/sample.h5ad", "sample"),
        ("", "sample"),
        ("../../escape.h5ad", "escape"),
    ],
)
def test_sample_names_are_reduced_to_a_safe_base_name(raw_name, expected) -> None:
    assert SimBuParameters.sanitize_sample_name(raw_name) == expected


def test_a_sample_count_below_one_is_refused() -> None:
    with pytest.raises(ValidationError):
        SimBuParameters.create(0.2, 0, "sample")


def test_the_emitted_paths_are_parsed_from_stdout() -> None:
    plot_path, counts_path = SimBuRunResult.parse_emitted_paths(
        "loading\nPDF: /out/tissues/simbu_icf_0.2.pdf\nTXT: /out/tissues/simbu_icf_0.2.txt\nOK\n"
    )

    assert plot_path == "/out/tissues/simbu_icf_0.2.pdf"
    assert counts_path == "/out/tissues/simbu_icf_0.2.txt"


# --- batch definitions -----------------------------------------------------


def test_a_comma_separated_batch_definition_is_parsed() -> None:
    rows = BatchDefinitionParser().parse(
        "input_file,fractions,n_samples,label\n"
        "tissue_a,0.01;0.02;0.05,500,tissueA\n"
        "tissue_b,1;2,300,tissueB\n"
    )

    assert len(rows) == 2
    assert rows[0].immune_cell_fractions == [0.01, 0.02, 0.05]
    assert rows[0].sample_count == 500
    # Values above 1 are read as percentages; exactly 1 stays a ratio and is
    # clamped to the SimBu maximum. See SimBuParameters.normalize_fraction.
    assert rows[1].immune_cell_fractions == [0.99, 0.02]


def test_a_tab_separated_batch_definition_is_parsed() -> None:
    rows = BatchDefinitionParser().parse(
        "input_file\tfractions\tn_samples\ntissue_a\t0.1\t50\n"
    )
    assert rows[0].label == "tissue_a"  # defaults to the input base name


def test_a_missing_column_is_reported() -> None:
    with pytest.raises(ValidationError, match="missing the column"):
        BatchDefinitionParser().parse("input_file,n_samples\ntissue_a,50\n")


def test_a_bad_sample_count_names_the_offending_line() -> None:
    with pytest.raises(ValidationError, match="Line 3"):
        BatchDefinitionParser().parse(
            "input_file,fractions,n_samples\n"
            "tissue_a,0.1,50\n"
            "tissue_b,0.1,not-a-number\n"
        )


# --- catalogue -------------------------------------------------------------


def test_the_catalogue_is_parsed_and_sorted(tmp_path: Path) -> None:
    (tmp_path / "catalog_ct1.txt").write_text(
        "gondal2025_ad076.h5ad;Multi-tumour (Gondal)\n"
        "pelka2021_ad076.h5ad;Colorectal (Pelka)\n",
        encoding="utf-8",
    )

    experiments = ExperimentCatalogService(tmp_path).list_experiments()

    assert [item.tissue_name for item in experiments] == [
        "Colorectal (Pelka)",
        "Multi-tumour (Gondal)",
    ]
    assert experiments[0].experiment_id == 0
    assert experiments[0].dataset_suffix == "ct1"
    assert (
        experiments[0].dataset_path(tmp_path).name == "combined_adata_ct1.h5ad"
    )


def test_a_windows_encoded_catalogue_file_is_still_read(tmp_path: Path) -> None:
    (tmp_path / "catalog_2a.txt").write_bytes(
        "sample.h5ad;Liver 37\xb0C\n".encode("cp1252")
    )

    experiments = ExperimentCatalogService(tmp_path).list_experiments()

    assert len(experiments) == 1
    assert "Liver" in experiments[0].tissue_name


def test_an_empty_catalogue_directory_yields_no_experiments(tmp_path: Path) -> None:
    assert ExperimentCatalogService(tmp_path / "missing").list_experiments() == []


def test_the_display_label_combines_tissue_and_experiment() -> None:
    experiment = Experiment(0, "catalog_3.txt", "exp3_c2_ad076.h5ad", "Pan-Cancer")
    assert experiment.display_label == "Pan-Cancer – exp3_c2_ad076.h5ad"


# --- cell type selection ---------------------------------------------------


def test_an_empty_cell_type_selection_is_refused() -> None:
    with pytest.raises(ValidationError):
        CellTypeSelection.from_mapping({"experiment_a": []}).require_non_empty()


def test_the_all_sentinel_is_recognised() -> None:
    selection = CellTypeSelection.from_mapping(
        {"experiment_a": ["ALL"], "experiment_b": ["T cell"]}
    )

    assert selection.selects_every_cell_type("experiment_a")
    assert not selection.selects_every_cell_type("experiment_b")
    assert selection.cell_types_for("experiment_b") == ["T cell"]


# --- metrics ---------------------------------------------------------------


def test_metrics_are_derived_from_the_confusion_matrix() -> None:
    matrix = ConfusionMatrix.from_h2o_table([[80, 20], [10, 90]])

    assert matrix.true_negatives == 80
    assert matrix.true_positives == 90
    assert matrix.sensitivity == pytest.approx(0.9)
    assert matrix.specificity == pytest.approx(0.8)
    assert matrix.precision == pytest.approx(90 / 110)
    assert matrix.f1_score == pytest.approx(2 * (90 / 110) * 0.9 / ((90 / 110) + 0.9))


def test_an_empty_confusion_matrix_does_not_divide_by_zero() -> None:
    matrix = ConfusionMatrix(0, 0, 0, 0)

    assert matrix.sensitivity == 0.0
    assert matrix.specificity == 0.0
    assert matrix.precision == 0.0
    assert matrix.f1_score == 0.0
