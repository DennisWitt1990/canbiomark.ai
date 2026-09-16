"""Finding single-cell datasets online and importing them into the catalogue."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .errors import ValidationError
from .job import JobStatus

# EBI accessions such as E-MTAB-10553, E-HCAD-10, E-GEOD-86618, S-EPMC1234.
EBI_ACCESSION_PATTERN = re.compile(r"^(E-[A-Z]+-\d+|S-[A-Z]+\d+)$", re.IGNORECASE)


class DatasetSource(str, Enum):
    """Where a dataset is fetched from."""

    CELLXGENE = "cellxgene"
    EBI_BIOSTUDIES = "ebi_biostudies"

    @classmethod
    def parse(cls, raw_value: str) -> "DatasetSource":
        normalized = (raw_value or "").strip().lower()
        for source in cls:
            if source.value == normalized:
                return source
        raise ValidationError(
            f"Unknown dataset source {raw_value!r}. Valid values: "
            + ", ".join(source.value for source in cls)
        )

    @property
    def display_name(self) -> str:
        return {
            DatasetSource.CELLXGENE: "CELLxGENE Discover",
            DatasetSource.EBI_BIOSTUDIES: "EBI BioStudies / Single Cell Expression Atlas",
        }[self]


@dataclass(frozen=True)
class RemoteDataset:
    """One dataset found online, as shown in the search results."""

    source: DatasetSource
    dataset_id: str
    title: str
    collection_name: str = ""
    organisms: List[str] = field(default_factory=list)
    tissues: List[str] = field(default_factory=list)
    diseases: List[str] = field(default_factory=list)
    assays: List[str] = field(default_factory=list)
    cell_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    publication_doi: str = ""
    landing_page_url: str = ""
    # Identifier the downloader needs; for CELLxGENE this is the version id.
    download_reference: str = ""

    @property
    def is_human(self) -> bool:
        return any("homo sapiens" in organism.lower() for organism in self.organisms)

    @property
    def file_size_megabytes(self) -> Optional[float]:
        if self.file_size_bytes is None:
            return None
        return round(self.file_size_bytes / (1024 * 1024), 1)

    def matches_organism_filter(self, required_organism: Optional[str]) -> bool:
        if not required_organism:
            return True
        needle = required_organism.strip().lower()
        return any(needle in organism.lower() for organism in self.organisms)


class ImportStage(str, Enum):
    """The steps an import goes through, in order."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    INSPECTING = "inspecting"
    AWAITING_CELL_TYPE_COLUMN = "awaiting_cell_type_column"
    CONVERTING = "converting"
    VERIFYING = "verifying"
    PUBLISHING = "publishing"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def needs_user_input(self) -> bool:
        return self is ImportStage.AWAITING_CELL_TYPE_COLUMN

    @property
    def is_terminal(self) -> bool:
        return self in {
            ImportStage.FINISHED,
            ImportStage.FAILED,
            ImportStage.CANCELLED,
        }


@dataclass
class DatasetImportJob:
    """One dataset being downloaded, annotated and published to the catalogue.

    The import deliberately **pauses** at
    :attr:`ImportStage.AWAITING_CELL_TYPE_COLUMN` rather than guessing when no
    cell type column is obvious. A wrong cell type silently corrupts every
    simulation built on the dataset, so a person confirms the choice.
    """

    job_id: str
    owner_user_id: str
    remote_dataset: RemoteDataset
    catalogue_name: str
    staging_directory: Path
    stage: ImportStage = ImportStage.QUEUED
    status: JobStatus = JobStatus.QUEUED
    completed_fraction: float = 0.0
    message: str = "Queued."
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    downloaded_bytes: int = 0
    expected_bytes: Optional[int] = None
    downloaded_file: Optional[Path] = None
    published_dataset_file: Optional[Path] = None
    published_catalogue_file: Optional[Path] = None

    selected_cell_type_column: Optional[str] = None
    cell_count: Optional[int] = None
    gene_count: Optional[int] = None
    distinct_cell_type_count: Optional[int] = None

    def touch(self) -> None:
        self.updated_at = time.time()

    @property
    def download_percent(self) -> float:
        if not self.expected_bytes:
            return 0.0
        return round(min(100.0, self.downloaded_bytes / self.expected_bytes * 100), 1)

    @property
    def is_waiting_for_user(self) -> bool:
        return self.stage.needs_user_input

    @staticmethod
    def sanitize_catalogue_name(raw_name: str) -> str:
        """A short, filesystem-safe identifier used for the catalogue entry.

        It becomes part of ``combined_adata_<name>.h5ad`` and ``catalog_<name>.txt``,
        so it must not contain separators or spaces.
        """
        candidate = (raw_name or "").strip().lower()
        candidate = re.sub(r"[^a-z0-9_-]+", "_", candidate).strip("_-")
        if not candidate:
            raise ValidationError(
                "The catalogue name must contain at least one letter or digit."
            )
        if len(candidate) > 48:
            candidate = candidate[:48].rstrip("_-")
        return candidate
