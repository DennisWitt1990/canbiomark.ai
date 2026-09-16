"""Wire format of the synthetic tissue generator, single runs and batches."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from ...domain.simbu import BatchJob, BatchTask, SimBuRunResult


class TissueUploadResponse(BaseModel):
    """Where an uploaded dataset was stored."""

    stored_path: str
    sample_base_name: str


class RunSimulationRequest(BaseModel):
    """Parameters of a single SimBu run."""

    immune_cell_fraction: float = Field(..., ge=0, le=99)
    sample_count: int = Field(..., ge=1, le=100_000)
    sample_base_name: str = Field(..., min_length=1, max_length=200)


class RunSimulationResponse(BaseModel):
    """Outcome of a single SimBu run."""

    succeeded: bool
    return_code: int
    standard_output: str
    standard_error: str
    plot_path: Optional[str] = None
    counts_path: Optional[str] = None
    input_source: Optional[str] = None
    input_path: Optional[str] = None
    run_id: Optional[str] = None

    @classmethod
    def from_result(cls, result: SimBuRunResult) -> "RunSimulationResponse":
        return cls(
            succeeded=result.succeeded,
            return_code=result.return_code,
            standard_output=result.standard_output,
            standard_error=result.standard_error,
            plot_path=result.plot_relative_path,
            counts_path=result.counts_relative_path,
            input_source=result.input_source,
            input_path=result.input_relative_path,
            run_id=result.run_id,
        )


class BatchDefinitionResponse(BaseModel):
    """Validation result of an uploaded batch definition file."""

    definition_path: str
    row_count: int
    planned_task_count: int


class StartBatchRequest(BaseModel):
    """Start a batch from a previously uploaded definition file."""

    definition_path: str = Field(..., min_length=1)


class BatchTaskResponse(BaseModel):
    """One simulation inside a batch."""

    label: str
    immune_cell_fraction: float
    sample_count: int
    status: str
    error_message: str

    @classmethod
    def from_task(cls, task: BatchTask) -> "BatchTaskResponse":
        return cls(
            label=task.label,
            immune_cell_fraction=task.parameters.immune_cell_fraction,
            sample_count=task.parameters.sample_count,
            status=task.status.value,
            error_message=task.error_message,
        )


class BatchJobResponse(BaseModel):
    """Status of a whole batch."""

    job_id: str
    status: str
    task_count: int
    finished_task_count: int
    failed_task_count: int
    completed_percent: float
    created_at: float
    updated_at: float
    tasks: List[BatchTaskResponse] = []

    @classmethod
    def from_job(cls, job: BatchJob, include_tasks: bool = True) -> "BatchJobResponse":
        return cls(
            job_id=job.job_id,
            status=job.status.value,
            task_count=job.task_count,
            finished_task_count=job.finished_task_count,
            failed_task_count=job.failed_task_count,
            completed_percent=job.completed_percent,
            created_at=job.created_at,
            updated_at=job.updated_at,
            tasks=[BatchTaskResponse.from_task(task) for task in job.tasks]
            if include_tasks
            else [],
        )
