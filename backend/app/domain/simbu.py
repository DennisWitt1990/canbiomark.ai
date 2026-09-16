"""Domain objects for synthetic tissue generation with SimBu."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .errors import ValidationError
from .job import JobStatus

MAXIMUM_IMMUNE_FRACTION = 0.99


@dataclass(frozen=True)
class SimBuParameters:
    """Validated inputs of one SimBu simulation."""

    immune_cell_fraction: float
    sample_count: int
    sample_base_name: str

    @staticmethod
    def normalize_fraction(raw_fraction: float) -> float:
        """Accept both percentages (0..99) and ratios (0..0.99).

        Anything above 1 is read as a percentage and divided by 100; anything
        at or below 1 is already a ratio.  Exactly ``1`` is therefore read as
        "the whole tissue" and clamped to :data:`MAXIMUM_IMMUNE_FRACTION`, not
        as one percent -- write ``0.01`` when you mean one percent.  This
        matches the behaviour of the original implementation, so batch files
        written for it keep producing identical results.
        """
        fraction = float(raw_fraction)
        if fraction > 1.0:
            fraction = fraction / 100.0
        return max(0.0, min(MAXIMUM_IMMUNE_FRACTION, fraction))

    @staticmethod
    def sanitize_sample_name(raw_name: str, fallback: str = "sample") -> str:
        """Reduce an arbitrary string to a safe base name without extension."""
        candidate = (raw_name or "").strip()
        if not candidate:
            return fallback
        candidate = Path(candidate).name
        if candidate.lower().endswith(".h5ad"):
            candidate = candidate[: -len(".h5ad")]
        return candidate or fallback

    @classmethod
    def create(
        cls, immune_cell_fraction: float, sample_count: int, sample_base_name: str
    ) -> "SimBuParameters":
        if sample_count < 1:
            raise ValidationError("The number of samples must be at least 1.")
        return cls(
            immune_cell_fraction=cls.normalize_fraction(immune_cell_fraction),
            sample_count=int(sample_count),
            sample_base_name=cls.sanitize_sample_name(sample_base_name),
        )

    @property
    def fraction_label(self) -> str:
        """Compact label used in directory names, e.g. ``0.02`` -> ``0.02``."""
        return f"{self.immune_cell_fraction:.4f}".rstrip("0").rstrip(".") or "0"


@dataclass
class SimBuRunResult:
    """Outcome of a single ``Rscript`` invocation."""

    succeeded: bool
    return_code: int
    standard_output: str
    standard_error: str
    plot_relative_path: Optional[str] = None
    counts_relative_path: Optional[str] = None
    input_source: str = "workspace"
    input_relative_path: Optional[str] = None
    run_id: Optional[str] = None

    @staticmethod
    def parse_emitted_paths(standard_output: str) -> tuple[Optional[str], Optional[str]]:
        """The R script prints ``PDF:``/``TXT:`` lines with absolute paths."""
        plot_path: Optional[str] = None
        counts_path: Optional[str] = None
        for line in standard_output.splitlines():
            if line.startswith("PDF:"):
                plot_path = line[len("PDF:") :].strip()
            elif line.startswith("TXT:"):
                counts_path = line[len("TXT:") :].strip()
        return plot_path, counts_path


@dataclass
class BatchTask:
    """One simulation inside a batch: a single dataset at a single fraction."""

    source_dataset: Path
    parameters: SimBuParameters
    label: str
    status: JobStatus = JobStatus.QUEUED
    error_message: str = ""
    output_directory: Optional[Path] = None

    @property
    def is_finished(self) -> bool:
        return self.status in {JobStatus.FINISHED, JobStatus.FAILED}


@dataclass
class BatchJob:
    """A queue of :class:`BatchTask` objects belonging to one user."""

    job_id: str
    owner_user_id: str
    tasks: List[BatchTask]
    results_directory: Path
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error_message: Optional[str] = None
    definition_file: Optional[Path] = None
    shared_input_directory: Optional[Path] = None

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    @property
    def finished_task_count(self) -> int:
        return sum(1 for task in self.tasks if task.is_finished)

    @property
    def failed_task_count(self) -> int:
        return sum(1 for task in self.tasks if task.status is JobStatus.FAILED)

    @property
    def completed_percent(self) -> float:
        if self.task_count == 0:
            return 0.0
        return round(self.finished_task_count / self.task_count * 100, 1)

    def derive_final_status(self) -> JobStatus:
        if self.failed_task_count == self.task_count and self.task_count > 0:
            return JobStatus.FAILED
        if self.failed_task_count > 0:
            return JobStatus.FINISHED_WITH_ERRORS
        return JobStatus.FINISHED

    def touch(self) -> None:
        self.updated_at = time.time()
