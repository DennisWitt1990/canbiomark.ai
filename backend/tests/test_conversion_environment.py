"""The dataset conversion runs in its own interpreter, and must.

The application is pinned to ``anndata==0.7.6`` so that SeuratDisk -- and hence
SimBu -- can read what it writes. That same version cannot *read* the files
CELLxGENE and EBI publish, which modern anndata wrote. The container therefore
carries a second environment used only for the conversion step.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from packaging.version import Version

from app.domain.dataset_import import DatasetSource, RemoteDataset

CONVERSION_TOOL_MODULE = "app.tools.convert_dataset"
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def has_modern_anndata() -> bool:
    try:
        import anndata

        return Version(anndata.__version__) >= Version("0.10")
    except Exception:  # noqa: BLE001
        return False


needs_modern_anndata = pytest.mark.skipif(
    not has_modern_anndata(),
    reason="requires a modern anndata, as the conversion environment has",
)


def write_modern_dataset(target_path: Path, cell_types: list[str]) -> None:
    """Write a file with exactly the features anndata 0.7.6 cannot read."""
    import anndata
    import numpy
    import pandas
    from scipy import sparse

    cell_count = len(cell_types)
    observations = pandas.DataFrame(
        {
            "author_labels": pandas.Categorical(cell_types),
            "quality": pandas.array([1, None] * (cell_count // 2), dtype="Int64"),
        },
        index=[f"cell{index}" for index in range(cell_count)],
    )
    variables = pandas.DataFrame(
        {"feature_name": pandas.Categorical([f"GENE{index}" for index in range(6)])},
        index=[f"ENSG{index:05d}" for index in range(6)],
    )
    dataset = anndata.AnnData(
        X=sparse.random(cell_count, 6, density=0.5, format="csr"),
        obs=observations,
        var=variables,
    )
    dataset.obsm["X_umap"] = numpy.random.rand(cell_count, 2)
    dataset.write_h5ad(target_path)


# --- the tool ---------------------------------------------------------------


@needs_modern_anndata
def test_the_tool_converts_a_modern_file_and_reports_what_it_did(
    tmp_path: Path,
) -> None:
    from app.services.anndata_compatibility import AnnDataCompatibilityConverter

    source_path = tmp_path / "modern.h5ad"
    target_path = tmp_path / "converted.h5ad"
    write_modern_dataset(source_path, ["T cell", "B cell"] * 5)

    # Sanity: the input really is unreadable for 0.7.6 before conversion.
    converter = AnnDataCompatibilityConverter()
    assert not converter.verify(source_path).is_readable

    completed = subprocess.run(
        [
            sys.executable, "-m", CONVERSION_TOOL_MODULE,
            "--input", str(source_path),
            "--output", str(target_path),
            "--cell-type-column", "author_labels",
            "--source-id", "unit-test",
        ],
        capture_output=True, text=True, cwd=str(BACKEND_ROOT),
    )
    assert completed.returncode == 0, completed.stderr

    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["ok"] is True
    assert report["cell_count"] == 10
    assert report["distinct_cell_types"] == 2

    # And the output is readable by the pinned reader.
    assert converter.verify(target_path).is_readable


@needs_modern_anndata
def test_the_tool_writes_the_cell_type_and_its_provenance(tmp_path: Path) -> None:
    import anndata

    source_path = tmp_path / "modern.h5ad"
    target_path = tmp_path / "converted.h5ad"
    write_modern_dataset(source_path, ["macrophage", "T cell"] * 5)

    subprocess.run(
        [
            sys.executable, "-m", CONVERSION_TOOL_MODULE,
            "--input", str(source_path), "--output", str(target_path),
            "--cell-type-column", "author_labels", "--source-id", "abc-123",
        ],
        check=True, capture_output=True, text=True, cwd=str(BACKEND_ROOT),
    )

    converted = anndata.read_h5ad(target_path)
    assert set(converted.obs["cell_type"]) == {"macrophage", "T cell"}
    assert set(converted.obs["source_dataset"]) == {"abc-123"}
    assert set(converted.obs["source_cell_type_column"]) == {"author_labels"}


@needs_modern_anndata
def test_an_unknown_column_fails_without_writing_an_output(tmp_path: Path) -> None:
    source_path = tmp_path / "modern.h5ad"
    target_path = tmp_path / "converted.h5ad"
    write_modern_dataset(source_path, ["T cell", "B cell"] * 5)

    completed = subprocess.run(
        [
            sys.executable, "-m", CONVERSION_TOOL_MODULE,
            "--input", str(source_path), "--output", str(target_path),
            "--cell-type-column", "no_such_column",
        ],
        capture_output=True, text=True, cwd=str(BACKEND_ROOT),
    )

    assert completed.returncode != 0
    assert "no_such_column" in (completed.stderr + completed.stdout)
    # A failed conversion must not leave something that looks importable.
    assert not target_path.exists()


# --- how the service decides which path to take -----------------------------


def test_the_service_uses_the_subprocess_only_when_one_is_configured(
    tmp_path: Path,
) -> None:
    """Configured executable means the container path; absent means in-process."""
    from app.jobs.background_worker import BackgroundWorker
    from app.jobs.job_registry import JobRegistry
    from app.services.anndata_compatibility import AnnDataCompatibilityConverter
    from app.services.dataset_download import DatasetDownloader
    from app.services.dataset_import_service import DatasetImportService
    from app.services.dataset_search_service import DatasetSearchService
    from app.services.h5ad_inspector import H5adInspector

    def build_service(conversion_python):
        return DatasetImportService(
            search_service=DatasetSearchService(),
            downloader=DatasetDownloader(),
            inspector=H5adInspector(),
            compatibility_converter=AnnDataCompatibilityConverter(),
            job_registry=JobRegistry("dataset import"),
            background_worker=BackgroundWorker(),
            catalogue_directory=tmp_path / "catalogue",
            staging_root=tmp_path / "staging",
            conversion_python_executable=conversion_python,
        )

    assert build_service("/opt/venv-conversion/bin/python")._conversion_python_executable
    assert build_service(None)._conversion_python_executable is None


def test_a_cellxgene_dataset_is_marked_for_raw_count_promotion() -> None:
    """CELLxGENE keeps raw counts in .raw.X; SimBu needs those, not .X."""
    cellxgene_dataset = RemoteDataset(
        source=DatasetSource.CELLXGENE, dataset_id="x", title="t"
    )
    ebi_dataset = RemoteDataset(
        source=DatasetSource.EBI_BIOSTUDIES, dataset_id="E-MTAB-1", title="t"
    )

    assert cellxgene_dataset.source is DatasetSource.CELLXGENE
    assert ebi_dataset.source is not DatasetSource.CELLXGENE
