"""Wire format of the AI suite."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from ...domain.analysis_task import AnalysisTask, RegressionModelKind
from ...services.ai_suite_service import AiSuiteJob


class CreateAiSuiteJobRequest(BaseModel):
    """Name, task and -- for regression -- which estimators to fit."""

    run_name: str = Field(default="run_001", min_length=1, max_length=100)
    task: str = Field(default=AnalysisTask.CLASSIFICATION.value)
    regression_models: Optional[List[str]] = Field(default=None)

    def parsed_task(self) -> AnalysisTask:
        return AnalysisTask.parse(self.task)

    def parsed_regression_models(self) -> List[RegressionModelKind]:
        if self.regression_models is None:
            return RegressionModelKind.default_selection()
        return [RegressionModelKind.parse(name) for name in self.regression_models]


class AnalysisTaskOptionResponse(BaseModel):
    """One selectable task or model, for building the form."""

    value: str
    display_name: str


class AiSuiteOptionsResponse(BaseModel):
    """What the AI suite can be asked to do."""

    tasks: List[AnalysisTaskOptionResponse]
    regression_models: List[AnalysisTaskOptionResponse]
    classification_thresholds: List[float]


class AiSuiteJobResponse(BaseModel):
    """Status of an AI suite job."""

    job_id: str
    run_name: str
    task: str
    regression_models: List[str]
    status: str
    completed_fraction: float
    completed_percent: float
    message: str
    error_message: Optional[str] = None
    created_at: float
    updated_at: float

    @classmethod
    def from_job(cls, job: AiSuiteJob) -> "AiSuiteJobResponse":
        return cls(
            job_id=job.job_id,
            run_name=job.run_name,
            task=job.task.value,
            regression_models=[model.value for model in job.regression_models],
            status=job.status.value,
            completed_fraction=job.progress.completed_fraction,
            completed_percent=job.progress.completed_percent,
            message=job.progress.message,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class AiSuiteUploadResponse(BaseModel):
    """How many files were stored in which split."""

    job_id: str
    split: str
    uploaded_file_count: int


class AiSuiteResultsResponse(BaseModel):
    """The result folder of a finished job."""

    job_id: str
    status: str
    results_directory: str
    files: List[str]
    error_message: Optional[str] = None
