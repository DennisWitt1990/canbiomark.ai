"""Runs many SimBu simulations from one definition file (formerly "module 4 batch").

Disk and runtime optimisation kept from the original implementation: every
distinct source dataset is copied **once** into a shared ``_inputs`` directory
per job, so the expensive ``h5ad -> h5seurat`` conversion happens once and all
later tasks hit the cache.  Per-task output stays isolated.
"""
from __future__ import annotations

import csv
import json
import logging
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

from ..domain.errors import ResourceNotFoundError, ValidationError
from ..domain.job import JobStatus
from ..domain.simbu import BatchJob, BatchTask, SimBuParameters
from ..jobs.background_worker import BackgroundWorker
from ..jobs.job_registry import JobRegistry
from .batch_definition_parser import BatchDefinitionParser, BatchDefinitionRow
from .simbu_runner import SimBuInvocation, SimBuRunner
from .tissue_generator_service import DATASET_FILE_SUFFIX
from .workspace_service import UserWorkspace

_logger = logging.getLogger(__name__)

SHARED_INPUTS_DIRECTORY_NAME = "_inputs"
MANIFEST_FILE_NAME = "manifest.csv"
TASK_INFO_FILE_NAME = "task_info.json"
EXCLUDED_ARCHIVE_SUFFIXES = {".h5ad", ".h5seurat"}


@dataclass(frozen=True)
class BatchDefinitionPreview:
    """Result of validating a definition file without starting anything."""

    definition_relative_path: str
    row_count: int
    planned_task_count: int


class TissueBatchService:
    """Validates definition files, queues batch jobs and serves their results."""

    def __init__(
        self,
        *,
        simbu_runner: SimBuRunner,
        definition_parser: BatchDefinitionParser,
        job_registry: JobRegistry[BatchJob],
        background_worker: BackgroundWorker,
    ) -> None:
        self._simbu_runner = simbu_runner
        self._definition_parser = definition_parser
        self._job_registry = job_registry
        self._background_worker = background_worker

    # -- definition files ---------------------------------------------------

    def store_definition_file(
        self, workspace: UserWorkspace, file_name: str, raw_bytes: bytes
    ) -> BatchDefinitionPreview:
        """Validate a CSV/TSV upload and keep it for a later start."""
        self._assert_is_definition_file(file_name)
        raw_content = self._decode(raw_bytes)

        definition_rows = self._definition_parser.parse(raw_content)
        planned_tasks = self._build_tasks(workspace, definition_rows)

        pending_directory = workspace.ensure_directory(
            "tissue_generator/batch_definitions"
        )
        definition_path = pending_directory / f"{uuid.uuid4()}.csv"
        definition_path.write_bytes(raw_bytes)

        return BatchDefinitionPreview(
            definition_relative_path=workspace.to_relative_path(definition_path),
            row_count=len(definition_rows),
            planned_task_count=len(planned_tasks),
        )

    # -- job life cycle -----------------------------------------------------

    def start_batch(
        self, workspace: UserWorkspace, definition_relative_path: str
    ) -> BatchJob:
        definition_path = workspace.resolve(definition_relative_path)
        raw_content = definition_path.read_text(encoding="utf-8-sig", errors="replace")

        definition_rows = self._definition_parser.parse(raw_content)
        tasks = self._build_tasks(workspace, definition_rows)

        job_id = str(uuid.uuid4())
        results_directory = workspace.tissue_batches_directory / job_id
        results_directory.mkdir(parents=True, exist_ok=True)

        job = BatchJob(
            job_id=job_id,
            owner_user_id=workspace.user_id,
            tasks=tasks,
            results_directory=results_directory,
            status=JobStatus.QUEUED,
            definition_file=definition_path,
        )
        self._job_registry.register(job)
        self._background_worker.start(self._execute_batch, job_id)
        return job

    def get_job(self, workspace: UserWorkspace, job_id: str) -> BatchJob:
        return self._job_registry.get_for_owner(job_id, workspace.user_id)

    def list_jobs(self, workspace: UserWorkspace) -> List[BatchJob]:
        return self._job_registry.list_for_owner(
            workspace.user_id, sort_key=lambda job: job.created_at
        )

    def cancel_and_delete(self, workspace: UserWorkspace, job_id: str) -> None:
        job = self.get_job(workspace, job_id)
        self._job_registry.update(job_id, status=JobStatus.CANCELLED)
        self._job_registry.remove(job_id)

        results_directory = job.results_directory
        self._background_worker.start(
            lambda: shutil.rmtree(results_directory, ignore_errors=True)
        )

    def build_result_archive(self, workspace: UserWorkspace, job_id: str) -> Path:
        """Zip the per-task outputs; returns the archive path."""
        job = self.get_job(workspace, job_id)
        if not job.status.has_results:
            raise ValidationError(
                f"The batch is not finished yet (status: {job.status.value})."
            )

        self._write_manifest(job)
        archive_path = job.results_directory / f"batch_{job_id[:8]}.zip"

        with zipfile.ZipFile(
            archive_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            manifest_path = job.results_directory / MANIFEST_FILE_NAME
            if manifest_path.exists():
                archive.write(manifest_path, arcname=MANIFEST_FILE_NAME)

            for task in job.tasks:
                if task.output_directory is None:
                    continue
                for entry in task.output_directory.rglob("*"):
                    if not entry.is_file():
                        continue
                    if entry.suffix.lower() in EXCLUDED_ARCHIVE_SUFFIXES:
                        continue  # keep multi-gigabyte inputs out of the archive
                    archive.write(
                        entry, arcname=str(entry.relative_to(job.results_directory))
                    )

        return archive_path

    # -- worker -------------------------------------------------------------

    def _execute_batch(self, job_id: str) -> None:
        """Sequential worker body; runs in a background thread."""
        job = self._job_registry.find(job_id)
        if job is None:
            return

        self._job_registry.update(job_id, status=JobStatus.RUNNING)

        try:
            shared_input_directory = self._prepare_shared_inputs(job)
            self._job_registry.update(
                job_id, shared_input_directory=shared_input_directory
            )
        except OSError as error:
            _logger.exception("Could not prepare shared inputs for job %s", job_id)
            for task in job.tasks:
                task.status = JobStatus.FAILED
                task.error_message = f"Could not prepare the shared inputs: {error}"
            self._job_registry.update(job_id, status=JobStatus.FAILED)
            self._write_manifest(job)
            return

        for task in job.tasks:
            current_job = self._job_registry.find(job_id)
            if current_job is None or current_job.status is JobStatus.CANCELLED:
                _logger.info("Batch %s was cancelled; stopping.", job_id)
                return

            task.output_directory = job.results_directory / task.label
            self._execute_single_task(task, shared_input_directory)
            self._job_registry.update(job_id)
            self._write_manifest(job)

        final_job = self._job_registry.find(job_id)
        if final_job is None or final_job.status is JobStatus.CANCELLED:
            return

        self._job_registry.update(job_id, status=final_job.derive_final_status())
        self._write_manifest(final_job)

    def _execute_single_task(self, task: BatchTask, shared_input_directory: Path) -> None:
        task.status = JobStatus.RUNNING
        assert task.output_directory is not None
        task.output_directory.mkdir(parents=True, exist_ok=True)

        result = self._simbu_runner.run(
            SimBuInvocation(
                input_directory=shared_input_directory,
                output_directory=task.output_directory,
                parameters=task.parameters,
            )
        )

        if result.succeeded:
            task.status = JobStatus.FINISHED
            task.error_message = ""
        else:
            task.status = JobStatus.FAILED
            task.error_message = (
                f"return code {result.return_code}\n{result.standard_error[-1000:]}"
            )

        self._write_task_info(task)

    # -- helpers ------------------------------------------------------------

    def _build_tasks(
        self, workspace: UserWorkspace, definition_rows: List[BatchDefinitionRow]
    ) -> List[BatchTask]:
        tasks: List[BatchTask] = []
        problems: List[str] = []

        for row in definition_rows:
            try:
                dataset_path = self._resolve_dataset(workspace, row.input_reference)
            except ResourceNotFoundError as error:
                problems.append(f"Line {row.line_number}: {error.message}")
                continue

            for fraction in row.immune_cell_fractions:
                parameters = SimBuParameters.create(
                    immune_cell_fraction=fraction,
                    sample_count=row.sample_count,
                    sample_base_name=dataset_path.stem,
                )
                tasks.append(
                    BatchTask(
                        source_dataset=dataset_path,
                        parameters=parameters,
                        label=f"{row.label}_frac{parameters.fraction_label}",
                    )
                )

        if problems:
            raise ValidationError(
                "Some datasets referenced by the batch file are missing:\n"
                + "\n".join(problems)
            )
        if not tasks:
            raise ValidationError("The batch file produced no runnable task.")
        return tasks

    @staticmethod
    def _resolve_dataset(workspace: UserWorkspace, input_reference: str) -> Path:
        """Look the dataset up in uploads, then cell selection, then by path."""
        base_name = SimBuParameters.sanitize_sample_name(input_reference)
        file_name = f"{base_name}{DATASET_FILE_SUFFIX}"

        for candidate in (
            workspace.tissue_uploads_directory / file_name,
            workspace.cell_selection_directory / file_name,
        ):
            if candidate.exists():
                return candidate

        if "/" in input_reference or input_reference.lower().endswith(
            DATASET_FILE_SUFFIX
        ):
            try:
                return workspace.resolve(input_reference)
            except Exception:  # noqa: BLE001 - fall through to the error below
                pass

        raise ResourceNotFoundError(
            f"No dataset '{file_name}' in your workspace. Upload it first."
        )

    @staticmethod
    def _prepare_shared_inputs(job: BatchJob) -> Path:
        """Copy every distinct source dataset exactly once into ``_inputs``."""
        shared_directory = job.results_directory / SHARED_INPUTS_DIRECTORY_NAME
        shared_directory.mkdir(parents=True, exist_ok=True)

        already_copied: Set[Path] = set()
        for task in job.tasks:
            source_path = task.source_dataset.resolve()
            if source_path in already_copied:
                continue
            already_copied.add(source_path)

            target_path = shared_directory / source_path.name
            if target_path.exists():
                try:
                    if target_path.stat().st_mtime >= source_path.stat().st_mtime:
                        continue  # a usable copy is already in place
                except OSError:
                    pass
            shutil.copy2(source_path, target_path)

        return shared_directory

    @staticmethod
    def _write_task_info(task: BatchTask) -> None:
        if task.output_directory is None:
            return
        task_info = {
            "label": task.label,
            "source_dataset": task.source_dataset.name,
            "source_dataset_path": str(task.source_dataset),
            "immune_cell_fraction": task.parameters.immune_cell_fraction,
            "sample_count": task.parameters.sample_count,
            "status": task.status.value,
            "error": task.error_message or None,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        try:
            (task.output_directory / TASK_INFO_FILE_NAME).write_text(
                json.dumps(task_info, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            _logger.warning("Could not write %s for task %s", TASK_INFO_FILE_NAME, task.label)

    @staticmethod
    def _write_manifest(job: BatchJob) -> None:
        """Provenance file listing every task and its outcome."""
        manifest_path = job.results_directory / MANIFEST_FILE_NAME
        try:
            with manifest_path.open("w", newline="", encoding="utf-8") as manifest_file:
                writer = csv.writer(manifest_file)
                writer.writerow(
                    [
                        "label",
                        "source_dataset",
                        "source_dataset_path",
                        "immune_cell_fraction",
                        "sample_count",
                        "status",
                        "error",
                    ]
                )
                for task in job.tasks:
                    writer.writerow(
                        [
                            task.label,
                            task.source_dataset.name,
                            str(task.source_dataset),
                            task.parameters.immune_cell_fraction,
                            task.parameters.sample_count,
                            task.status.value,
                            task.error_message,
                        ]
                    )
        except OSError:
            _logger.warning("Could not write the manifest for job %s", job.job_id)

    @staticmethod
    def _assert_is_definition_file(file_name: str) -> None:
        if not (file_name or "").lower().endswith((".csv", ".tsv")):
            raise ValidationError("Only .csv or .tsv batch files are accepted.")

    @staticmethod
    def _decode(raw_bytes: bytes) -> str:
        try:
            return raw_bytes.decode("utf-8-sig")  # tolerate a byte-order mark
        except UnicodeDecodeError:
            return raw_bytes.decode("latin-1")
