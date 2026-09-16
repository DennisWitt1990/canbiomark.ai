"""Wire format of the dataset importer."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from ...domain.cell_type_column import CellTypeColumnCandidate
from ...domain.dataset_import import DatasetImportJob, DatasetSource, RemoteDataset


class DatasetSearchRequest(BaseModel):
    """A search against one of the remote catalogues."""

    source: str = Field(default=DatasetSource.CELLXGENE.value)
    query: str = Field(default="", max_length=200)
    organism: Optional[str] = Field(default="Homo sapiens", max_length=80)
    limit: int = Field(default=40, ge=1, le=200)

    def parsed_source(self) -> DatasetSource:
        return DatasetSource.parse(self.source)


class RemoteDatasetResponse(BaseModel):
    """One dataset in the search results."""

    source: str
    dataset_id: str
    title: str
    collection_name: str
    organisms: List[str]
    tissues: List[str]
    diseases: List[str]
    assays: List[str]
    cell_count: Optional[int]
    file_size_megabytes: Optional[float]
    publication_doi: str
    landing_page_url: str
    download_reference: str

    @classmethod
    def from_dataset(cls, dataset: RemoteDataset) -> "RemoteDatasetResponse":
        return cls(
            source=dataset.source.value,
            dataset_id=dataset.dataset_id,
            title=dataset.title,
            collection_name=dataset.collection_name,
            organisms=dataset.organisms,
            tissues=dataset.tissues,
            diseases=dataset.diseases,
            assays=dataset.assays,
            cell_count=dataset.cell_count,
            file_size_megabytes=dataset.file_size_megabytes,
            publication_doi=dataset.publication_doi,
            landing_page_url=dataset.landing_page_url,
            download_reference=dataset.download_reference,
        )

    def to_dataset(self) -> RemoteDataset:
        return RemoteDataset(
            source=DatasetSource.parse(self.source),
            dataset_id=self.dataset_id,
            title=self.title,
            collection_name=self.collection_name,
            organisms=self.organisms,
            tissues=self.tissues,
            diseases=self.diseases,
            assays=self.assays,
            cell_count=self.cell_count,
            publication_doi=self.publication_doi,
            landing_page_url=self.landing_page_url,
            download_reference=self.download_reference,
        )


class StartImportRequest(BaseModel):
    """Begin importing one of the datasets found by a search."""

    dataset: RemoteDatasetResponse
    catalogue_name: str = Field(..., min_length=1, max_length=48)


class ColumnCandidateResponse(BaseModel):
    """One observation column, with what it contains and why it scored as it did."""

    column_name: str
    score: float
    is_known_name: bool
    is_usable: bool
    distinct_value_count: int
    total_cells: int
    missing_fraction: float
    most_frequent_values: List[dict]
    reasons: List[str]

    @classmethod
    def from_candidate(
        cls, candidate: CellTypeColumnCandidate
    ) -> "ColumnCandidateResponse":
        summary = candidate.summary
        return cls(
            column_name=candidate.column_name,
            score=round(candidate.score, 1),
            is_known_name=candidate.is_known_name,
            is_usable=candidate.is_usable,
            distinct_value_count=summary.distinct_value_count,
            total_cells=summary.total_cells,
            missing_fraction=round(summary.missing_fraction, 4),
            most_frequent_values=[
                {"value": value, "count": count}
                for value, count in summary.most_frequent_values
            ],
            reasons=candidate.reasons,
        )


class CellTypeDecisionResponse(BaseModel):
    """Everything the column selection dialog needs."""

    job_id: str
    dataset_title: str
    recommended_column: Optional[str]
    candidates: List[ColumnCandidateResponse]


class ConfirmCellTypeColumnRequest(BaseModel):
    """The column the administrator picked."""

    column_name: str = Field(..., min_length=1, max_length=300)


class DatasetImportJobResponse(BaseModel):
    """Progress of one import."""

    job_id: str
    stage: str
    status: str
    completed_percent: float
    message: str
    error_message: Optional[str]
    dataset_title: str
    source: str
    catalogue_name: str
    is_waiting_for_user: bool
    download_percent: float
    downloaded_megabytes: float
    expected_megabytes: Optional[float]
    cell_count: Optional[int]
    gene_count: Optional[int]
    selected_cell_type_column: Optional[str]
    distinct_cell_type_count: Optional[int]
    published_file_name: Optional[str]
    created_at: float
    updated_at: float

    @classmethod
    def from_job(cls, job: DatasetImportJob) -> "DatasetImportJobResponse":
        megabyte = 1024 * 1024
        return cls(
            job_id=job.job_id,
            stage=job.stage.value,
            status=job.status.value,
            completed_percent=round(job.completed_fraction * 100, 1),
            message=job.message,
            error_message=job.error_message,
            dataset_title=job.remote_dataset.title,
            source=job.remote_dataset.source.value,
            catalogue_name=job.catalogue_name,
            is_waiting_for_user=job.is_waiting_for_user,
            download_percent=job.download_percent,
            downloaded_megabytes=round(job.downloaded_bytes / megabyte, 1),
            expected_megabytes=(
                round(job.expected_bytes / megabyte, 1) if job.expected_bytes else None
            ),
            cell_count=job.cell_count,
            gene_count=job.gene_count,
            selected_cell_type_column=job.selected_cell_type_column,
            distinct_cell_type_count=job.distinct_cell_type_count,
            published_file_name=(
                job.published_dataset_file.name
                if job.published_dataset_file
                else None
            ),
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
