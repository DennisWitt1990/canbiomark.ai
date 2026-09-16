"""Single synthetic-tissue runs (formerly "module 4")."""
from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from ..domain.errors import ResourceNotFoundError, ValidationError
from ..domain.simbu import SimBuParameters, SimBuRunResult
from .cell_selection_service import FILTERED_DATASET_FILE_NAME
from .simbu_runner import SimBuInvocation, SimBuRunner
from .workspace_service import UserWorkspace

_logger = logging.getLogger(__name__)

DATASET_FILE_SUFFIX = ".h5ad"


@dataclass(frozen=True)
class DatasetLocation:
    """A dataset inside a workspace plus where it came from."""

    absolute_path: Path
    source: str  # "upload" or "cell_selection"


class TissueGeneratorService:
    """Uploads input datasets and runs a single SimBu simulation."""

    def __init__(self, simbu_runner: SimBuRunner) -> None:
        self._simbu_runner = simbu_runner

    # -- uploads -----------------------------------------------------------

    def store_uploaded_dataset(
        self, workspace: UserWorkspace, original_file_name: str, file_stream: BinaryIO
    ) -> str:
        """Save an uploaded ``.h5ad`` and return its workspace-relative path."""
        self.assert_is_dataset_file(original_file_name)
        sample_base_name = SimBuParameters.sanitize_sample_name(original_file_name)

        target_path = (
            workspace.tissue_uploads_directory / f"{sample_base_name}{DATASET_FILE_SUFFIX}"
        )
        workspace.assert_inside(target_path)

        with target_path.open("wb") as target_file:
            shutil.copyfileobj(file_stream, target_file)

        _logger.info("Stored uploaded dataset at %s", target_path)
        return workspace.to_relative_path(target_path)

    # -- running -----------------------------------------------------------

    def locate_input_dataset(
        self, workspace: UserWorkspace, sample_base_name: str
    ) -> DatasetLocation:
        """Prefer an uploaded dataset, fall back to the cell-selection output."""
        base_name = SimBuParameters.sanitize_sample_name(sample_base_name)
        file_name = f"{base_name}{DATASET_FILE_SUFFIX}"

        uploaded_path = workspace.tissue_uploads_directory / file_name
        if uploaded_path.exists():
            return DatasetLocation(absolute_path=uploaded_path, source="upload")

        cell_selection_path = workspace.cell_selection_directory / file_name
        if cell_selection_path.exists():
            return DatasetLocation(
                absolute_path=cell_selection_path, source="cell_selection"
            )

        raise ResourceNotFoundError(
            f"No dataset named '{file_name}' was found. Upload one in the tissue "
            f"generator, or run the cell selector first (it produces "
            f"'{FILTERED_DATASET_FILE_NAME}')."
        )

    def run_single_simulation(
        self, workspace: UserWorkspace, parameters: SimBuParameters
    ) -> SimBuRunResult:
        """Copy the input into an isolated run directory and simulate."""
        input_location = self.locate_input_dataset(
            workspace, parameters.sample_base_name
        )

        run_id = str(uuid.uuid4())
        run_directory = workspace.tissue_runs_directory / run_id
        run_directory.mkdir(parents=True, exist_ok=True)

        # The R script derives both the h5ad and the h5seurat cache path from
        # SIMBU_BASE_PATH, so the input has to live inside the run directory.
        run_input_path = (
            run_directory / f"{parameters.sample_base_name}{DATASET_FILE_SUFFIX}"
        )
        shutil.copy2(input_location.absolute_path, run_input_path)

        result = self._simbu_runner.run(
            SimBuInvocation(
                input_directory=run_directory,
                output_directory=run_directory,
                parameters=parameters,
            )
        )

        result.run_id = run_id
        result.input_source = input_location.source
        result.input_relative_path = workspace.to_relative_path(
            input_location.absolute_path
        )
        result.plot_relative_path = self._to_workspace_relative(
            workspace, run_directory, result.plot_relative_path
        )
        result.counts_relative_path = self._to_workspace_relative(
            workspace, run_directory, result.counts_relative_path
        )
        return result

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def assert_is_dataset_file(file_name: str) -> None:
        if not (file_name or "").lower().endswith(DATASET_FILE_SUFFIX):
            raise ValidationError(
                f"Only {DATASET_FILE_SUFFIX} files can be uploaded here."
            )

    @staticmethod
    def _to_workspace_relative(
        workspace: UserWorkspace, run_directory: Path, emitted_path: Optional[str]
    ) -> Optional[str]:
        """Convert an absolute path printed by the R script into a relative one."""
        if not emitted_path:
            return None

        absolute_candidate = Path(emitted_path)
        try:
            return workspace.to_relative_path(absolute_candidate)
        except Exception:  # noqa: BLE001 - fall back to a name-based lookup
            fallback_path = run_directory / absolute_candidate.name
            if fallback_path.exists():
                return workspace.to_relative_path(fallback_path)
            _logger.warning("Could not map emitted SimBu path %s", emitted_path)
            return None
