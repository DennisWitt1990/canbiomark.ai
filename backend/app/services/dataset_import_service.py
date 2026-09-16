"""Importing a remote dataset into the shared catalogue.

The pipeline is: download, inspect the observation columns, **wait for a person
to confirm the cell type column**, convert to an anndata 0.7.6 readable file,
verify, and publish into the shared data directory as
``combined_adata_<name>.h5ad`` with a matching ``catalog_<name>.txt``.

The pause is the point. A wrong cell type column does not fail loudly -- it
produces a dataset that simulates perfectly well and is quietly meaningless.
The importer therefore proposes a column, shows what each candidate actually
contains, and stops until somebody confirms.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..domain.cell_type_column import CellTypeColumnCandidate, CellTypeColumnScorer
from ..domain.dataset_import import (
    DatasetImportJob,
    DatasetSource,
    ImportStage,
    RemoteDataset,
)
from ..domain.errors import ValidationError
from ..domain.job import JobStatus
from ..jobs.background_worker import BackgroundWorker
from ..jobs.job_registry import JobRegistry
from .anndata_compatibility import AnnDataCompatibilityConverter
from .dataset_download import DatasetDownloader
from .dataset_search_service import DatasetSearchService
from .h5ad_inspector import H5adInspector

_logger = logging.getLogger(__name__)

CELL_TYPE_COLUMN = "cell_type"
CATALOGUE_DATASET_PREFIX = "combined_adata_"
CATALOGUE_INDEX_PREFIX = "catalog_"


@dataclass(frozen=True)
class CellTypeDecision:
    """What the importer found and what it suggests."""

    job_id: str
    candidates: List[CellTypeColumnCandidate]
    recommended_column: Optional[str]
    dataset_title: str


class DatasetImportService:
    """Downloads, annotates and publishes datasets into the shared catalogue."""

    def __init__(
        self,
        *,
        search_service: DatasetSearchService,
        downloader: DatasetDownloader,
        inspector: H5adInspector,
        compatibility_converter: AnnDataCompatibilityConverter,
        job_registry: JobRegistry[DatasetImportJob],
        background_worker: BackgroundWorker,
        catalogue_directory: Path,
        staging_root: Path,
        scorer: Optional[CellTypeColumnScorer] = None,
        conversion_python_executable: Optional[str] = None,
        conversion_timeout_seconds: int = 3600,
    ) -> None:
        self._search_service = search_service
        self._downloader = downloader
        self._inspector = inspector
        self._compatibility_converter = compatibility_converter
        self._job_registry = job_registry
        self._background_worker = background_worker
        self._catalogue_directory = Path(catalogue_directory)
        self._staging_root = Path(staging_root)
        self._scorer = scorer or CellTypeColumnScorer()
        # In the container this points at the modern-anndata interpreter; see
        # _convert_and_annotate for why a second environment is required.
        self._conversion_python_executable = conversion_python_executable
        self._conversion_timeout_seconds = conversion_timeout_seconds

    def discard_orphaned_staging_directories(self) -> int:
        """Remove staging folders left behind by a restart.

        The job registry lives in memory, so a restart during a download leaves
        a partially downloaded file with no job to finish it. Those folders can
        hold gigabytes, so they are cleared at start-up.
        """
        if not self._staging_root.exists():
            return 0

        removed_count = 0
        for staging_directory in self._staging_root.iterdir():
            if not staging_directory.is_dir():
                continue
            if self._job_registry.find(staging_directory.name) is not None:
                continue  # a live job still owns this folder
            shutil.rmtree(staging_directory, ignore_errors=True)
            removed_count += 1

        if removed_count:
            _logger.info(
                "Discarded %s orphaned import staging folder(s).", removed_count
            )
        return removed_count

    # -- starting an import -------------------------------------------------

    def start_import(
        self,
        *,
        administrator_user_id: str,
        remote_dataset: RemoteDataset,
        catalogue_name: str,
    ) -> DatasetImportJob:
        sanitized_name = DatasetImportJob.sanitize_catalogue_name(catalogue_name)
        self._assert_catalogue_name_free(sanitized_name)

        job_id = str(uuid.uuid4())
        staging_directory = self._staging_root / job_id
        staging_directory.mkdir(parents=True, exist_ok=True)

        job = DatasetImportJob(
            job_id=job_id,
            owner_user_id=administrator_user_id,
            remote_dataset=remote_dataset,
            catalogue_name=sanitized_name,
            staging_directory=staging_directory,
            expected_bytes=remote_dataset.file_size_bytes,
        )
        self._job_registry.register(job)
        self._background_worker.start(self._run_until_decision, job_id)
        return job

    def get_job(self, job_id: str, requesting_user_id: str) -> DatasetImportJob:
        return self._job_registry.get_for_owner(job_id, requesting_user_id)

    def list_jobs(self, requesting_user_id: str) -> List[DatasetImportJob]:
        return self._job_registry.list_for_owner(
            requesting_user_id, sort_key=lambda job: job.created_at
        )

    def cancel(self, job_id: str, requesting_user_id: str) -> None:
        job = self.get_job(job_id, requesting_user_id)
        self._job_registry.update(
            job_id, stage=ImportStage.CANCELLED, status=JobStatus.CANCELLED
        )
        staging_directory = job.staging_directory
        self._background_worker.start(
            lambda: shutil.rmtree(staging_directory, ignore_errors=True)
        )

    # -- the cell type decision --------------------------------------------

    def get_cell_type_decision(
        self, job_id: str, requesting_user_id: str
    ) -> CellTypeDecision:
        """The scored candidates for the paused job."""
        job = self.get_job(job_id, requesting_user_id)
        if job.downloaded_file is None or not job.downloaded_file.exists():
            raise ValidationError("The dataset has not been downloaded yet.")

        candidates = self._inspector.rank_cell_type_columns(job.downloaded_file)
        recommended = CellTypeColumnScorer.recommended(candidates)

        return CellTypeDecision(
            job_id=job.job_id,
            candidates=candidates,
            recommended_column=recommended.column_name if recommended else None,
            dataset_title=job.remote_dataset.title,
        )

    def confirm_cell_type_column(
        self, job_id: str, requesting_user_id: str, column_name: str
    ) -> DatasetImportJob:
        """Accept the chosen column and resume the import."""
        job = self.get_job(job_id, requesting_user_id)

        if job.stage is not ImportStage.AWAITING_CELL_TYPE_COLUMN:
            raise ValidationError(
                f"This import is not waiting for a column (stage: {job.stage.value})."
            )

        decision = self.get_cell_type_decision(job_id, requesting_user_id)
        chosen = next(
            (
                candidate
                for candidate in decision.candidates
                if candidate.column_name == column_name
            ),
            None,
        )
        if chosen is None:
            raise ValidationError(
                f"'{column_name}' is not an observation column of this dataset."
            )
        if not chosen.is_usable:
            raise ValidationError(
                f"'{column_name}' cannot be used as a cell type column: "
                + " ".join(chosen.reasons)
            )

        self._job_registry.update(
            job_id,
            selected_cell_type_column=column_name,
            distinct_cell_type_count=chosen.summary.distinct_value_count,
        )
        self._background_worker.start(self._run_after_decision, job_id)
        return self.get_job(job_id, requesting_user_id)

    # -- workers ------------------------------------------------------------

    def _run_until_decision(self, job_id: str) -> None:
        """Download and inspect, then pause for the cell type confirmation."""
        job = self._job_registry.find(job_id)
        if job is None:
            return

        try:
            self._report(job_id, ImportStage.DOWNLOADING, 0.02, "Starting the download ...")
            download_url = self._search_service.get_download_url(job.remote_dataset)
            target_path = job.staging_directory / "downloaded.h5ad"

            def report_download(downloaded_bytes: int, expected_bytes: Optional[int]) -> None:
                self._job_registry.update(
                    job_id,
                    downloaded_bytes=downloaded_bytes,
                    expected_bytes=expected_bytes,
                    completed_fraction=(
                        0.05 + 0.45 * (downloaded_bytes / expected_bytes)
                        if expected_bytes
                        else 0.1
                    ),
                    message=(
                        f"Downloading {downloaded_bytes // (1024 * 1024)} MB"
                        + (f" of {expected_bytes // (1024 * 1024)} MB" if expected_bytes else "")
                        + " ..."
                    ),
                )

            self._downloader.download(
                download_url,
                target_path,
                report_progress=report_download,
                should_cancel=lambda: self._is_cancelled(job_id),
            )
            if self._is_cancelled(job_id):
                return

            self._job_registry.update(job_id, downloaded_file=target_path)

            self._report(
                job_id, ImportStage.INSPECTING, 0.55, "Reading the observation columns ..."
            )
            cell_count, gene_count = self._inspector.read_dataset_shape(target_path)
            candidates = self._inspector.rank_cell_type_columns(target_path)
            recommended = CellTypeColumnScorer.recommended(candidates)

            self._job_registry.update(
                job_id,
                cell_count=cell_count,
                gene_count=gene_count,
                stage=ImportStage.AWAITING_CELL_TYPE_COLUMN,
                status=JobStatus.RUNNING,
                completed_fraction=0.6,
                message=(
                    f"{cell_count} cells x {gene_count} genes. "
                    + (
                        f"Suggested cell type column: '{recommended.column_name}'. "
                        "Confirm or choose another."
                        if recommended
                        else "No column could be identified as a cell type -- "
                        "please choose one."
                    )
                ),
            )

        except Exception as error:  # noqa: BLE001 - surfaced as job state
            _logger.exception("Dataset import %s failed during download.", job_id)
            self._fail(job_id, str(error))

    def _run_after_decision(self, job_id: str) -> None:
        """Convert, verify and publish once the column has been confirmed."""
        job = self._job_registry.find(job_id)
        if job is None or job.selected_cell_type_column is None:
            return

        try:
            self._report(
                job_id,
                ImportStage.CONVERTING,
                0.65,
                "Converting for anndata 0.7.6 (SimBu compatibility) ...",
            )
            converted_path = self._convert_and_annotate(job)
            if self._is_cancelled(job_id):
                return

            self._report(job_id, ImportStage.PUBLISHING, 0.92, "Publishing to the catalogue ...")
            dataset_file, catalogue_file = self._publish(job, converted_path)

            self._job_registry.update(
                job_id,
                stage=ImportStage.FINISHED,
                status=JobStatus.FINISHED,
                completed_fraction=1.0,
                published_dataset_file=dataset_file,
                published_catalogue_file=catalogue_file,
                message=f"Published as {dataset_file.name}.",
            )
            # The staging copy is redundant once the dataset is published.
            shutil.rmtree(job.staging_directory, ignore_errors=True)

        except Exception as error:  # noqa: BLE001 - surfaced as job state
            _logger.exception("Dataset import %s failed during conversion.", job_id)
            self._fail(job_id, str(error))

    # -- conversion and publishing -----------------------------------------

    def _convert_and_annotate(self, job: DatasetImportJob) -> Path:
        """Set ``obs['cell_type']`` from the chosen column and harden the file.

        This is delegated to a separate interpreter whenever one is configured.
        The application runs on ``anndata==0.7.6`` because SeuratDisk -- and
        therefore SimBu -- can only read what that version writes; but 0.7.6
        also cannot *read* the files that CELLxGENE and EBI publish, which
        modern anndata wrote. The container ships a second environment with a
        modern anndata purely for this step.

        Without such an interpreter configured the conversion runs in-process,
        which is correct for a development machine that already has a modern
        anndata installed.
        """
        assert job.downloaded_file is not None
        converted_path = job.staging_directory / "converted.h5ad"
        should_promote_raw = job.remote_dataset.source is DatasetSource.CELLXGENE

        if self._conversion_python_executable:
            self._convert_in_subprocess(
                job, converted_path, should_promote_raw=should_promote_raw
            )
        else:
            self._convert_in_process(
                job, converted_path, should_promote_raw=should_promote_raw
            )
        return converted_path

    def _convert_in_subprocess(
        self, job: DatasetImportJob, converted_path: Path, *, should_promote_raw: bool
    ) -> None:
        """Run the conversion tool under the modern-anndata interpreter."""
        assert job.downloaded_file is not None
        backend_root = Path(__file__).resolve().parents[2]

        command = [
            self._conversion_python_executable,
            "-m",
            "app.tools.convert_dataset",
            "--input",
            str(job.downloaded_file),
            "--output",
            str(converted_path),
            "--cell-type-column",
            str(job.selected_cell_type_column),
            "--source-id",
            job.remote_dataset.dataset_id,
        ]
        if should_promote_raw:
            command.append("--promote-raw")

        _logger.info("Converting dataset for import %s in a separate environment.", job.job_id)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(backend_root),
            timeout=self._conversion_timeout_seconds,
        )

        if completed.returncode != 0:
            raise ValidationError(
                "The dataset could not be converted for anndata 0.7.6:\n"
                + (completed.stderr or completed.stdout or "")[-1500:]
            )

        try:
            result = json.loads((completed.stdout or "").strip().splitlines()[-1])
        except (ValueError, IndexError) as error:
            raise ValidationError(
                "The conversion tool returned no usable result."
            ) from error

        self._job_registry.update(
            job.job_id,
            cell_count=result.get("cell_count", job.cell_count),
            gene_count=result.get("gene_count", job.gene_count),
            distinct_cell_type_count=result.get(
                "distinct_cell_types", job.distinct_cell_type_count
            ),
        )
        _logger.info("Import %s converted: %s", job.job_id, result)

    def _convert_in_process(
        self, job: DatasetImportJob, converted_path: Path, *, should_promote_raw: bool
    ) -> None:
        """Convert without a second interpreter; needs a modern anndata here."""
        import anndata

        assert job.downloaded_file is not None
        dataset = anndata.read_h5ad(job.downloaded_file)

        chosen_column = job.selected_cell_type_column
        if chosen_column not in dataset.obs.columns:
            raise ValidationError(
                f"'{chosen_column}' disappeared from the dataset between "
                f"inspection and conversion."
            )

        if should_promote_raw:
            dataset = self._promote_raw_counts_and_symbols(dataset)
            if chosen_column not in dataset.obs.columns:
                raise ValidationError(
                    f"'{chosen_column}' is not present after switching to the raw counts."
                )

        dataset.obs[CELL_TYPE_COLUMN] = dataset.obs[chosen_column].astype(str)
        dataset.obs["source_dataset"] = job.remote_dataset.dataset_id
        dataset.obs["source_cell_type_column"] = chosen_column

        self._job_registry.update(
            job.job_id,
            distinct_cell_type_count=int(dataset.obs[CELL_TYPE_COLUMN].nunique()),
        )

        report = self._compatibility_converter.write_readable(dataset, converted_path)
        _logger.info("Import %s conversion: %s", job.job_id, report.summary())
        del dataset

    @staticmethod
    def _promote_raw_counts_and_symbols(dataset):
        """Use ``.raw.X`` and HGNC symbols, as the CELLxGENE schema requires.

        Ported from the predecessor's ``fetch_cellxgene.py``: ``.X`` holds
        normalised values while SimBu needs raw counts, and ``var.index`` is an
        Ensembl id while the gene lists downstream use symbols.
        """
        import anndata

        if dataset.raw is not None:
            promoted = anndata.AnnData(
                X=dataset.raw.X, obs=dataset.obs.copy(), var=dataset.raw.var.copy()
            )
            promoted.obs_names = dataset.obs_names
            dataset = promoted
            _logger.info("Promoted .raw.X to .X (raw counts) for SimBu.")
        else:
            _logger.warning(
                "The dataset has no .raw; .X is assumed to hold raw counts, "
                "which is unusual for CELLxGENE."
            )

        if "feature_name" in dataset.var.columns:
            symbols = dataset.var["feature_name"].astype(str)
            duplicated = symbols.duplicated(keep="first")
            if duplicated.any():
                # First occurrence wins; counts are never summed silently.
                _logger.info(
                    "Dropped %s duplicate gene symbols.", int(duplicated.sum())
                )
                dataset = dataset[:, ~duplicated].copy()
                symbols = symbols[~duplicated]
            dataset.var_names = symbols.to_numpy()
            dataset.var_names.name = "gene_symbol"
        return dataset

    def _publish(self, job: DatasetImportJob, converted_path: Path) -> tuple[Path, Path]:
        """Move the dataset into the catalogue and write its index entry."""
        self._catalogue_directory.mkdir(parents=True, exist_ok=True)
        self._assert_catalogue_name_free(job.catalogue_name)

        dataset_file = (
            self._catalogue_directory
            / f"{CATALOGUE_DATASET_PREFIX}{job.catalogue_name}.h5ad"
        )
        catalogue_file = (
            self._catalogue_directory
            / f"{CATALOGUE_INDEX_PREFIX}{job.catalogue_name}.txt"
        )

        # move, not copy: the staging area may hold several gigabytes.
        shutil.move(str(converted_path), str(dataset_file))

        experiment_name = dataset_file.name
        tissue_label = self._build_tissue_label(job.remote_dataset)
        catalogue_file.write_text(
            f"{experiment_name};{tissue_label}\n", encoding="utf-8"
        )

        _logger.info("Published %s to the catalogue.", dataset_file.name)
        return dataset_file, catalogue_file

    @staticmethod
    def _build_tissue_label(remote_dataset: RemoteDataset) -> str:
        """The human-readable label shown in the cell selector."""
        tissue_part = ", ".join(remote_dataset.tissues[:3]) or "unspecified tissue"
        title_part = remote_dataset.title.strip() or remote_dataset.dataset_id
        label = f"{tissue_part} ({title_part})"
        # The catalogue format is semicolon separated and one line per entry.
        return label.replace(";", ",").replace("\n", " ")[:180]

    def _assert_catalogue_name_free(self, catalogue_name: str) -> None:
        dataset_file = (
            self._catalogue_directory
            / f"{CATALOGUE_DATASET_PREFIX}{catalogue_name}.h5ad"
        )
        if dataset_file.exists():
            raise ValidationError(
                f"A catalogue entry named '{catalogue_name}' already exists. "
                f"Choose a different name."
            )

    # -- job state helpers --------------------------------------------------

    def _is_cancelled(self, job_id: str) -> bool:
        job = self._job_registry.find(job_id)
        return job is None or job.stage is ImportStage.CANCELLED

    def _report(
        self, job_id: str, stage: ImportStage, completed_fraction: float, message: str
    ) -> None:
        self._job_registry.update(
            job_id,
            stage=stage,
            status=JobStatus.RUNNING,
            completed_fraction=completed_fraction,
            message=message,
        )

    def _fail(self, job_id: str, error_message: str) -> None:
        self._job_registry.update(
            job_id,
            stage=ImportStage.FAILED,
            status=JobStatus.FAILED,
            error_message=error_message,
            message="Failed.",
        )
