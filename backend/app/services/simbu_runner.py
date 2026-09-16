"""Thin, testable wrapper around the SimBu R script.

Both the single-run service and the batch service go through this class, so the
environment-variable contract with ``simbu.R`` is defined exactly once.
"""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..domain.errors import ResourceNotFoundError
from ..domain.simbu import SimBuParameters, SimBuRunResult

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimBuInvocation:
    """Where the R script reads its input and writes its output."""

    input_directory: Path
    output_directory: Path
    parameters: SimBuParameters


class SimBuRunner:
    """Executes ``Rscript simbu.R`` and captures its result."""

    def __init__(self, r_script_path: Path, timeout_seconds: int = 3600) -> None:
        self._r_script_path = Path(r_script_path)
        self._timeout_seconds = timeout_seconds

    @property
    def r_script_path(self) -> Path:
        return self._r_script_path

    def assert_script_available(self) -> None:
        if not self._r_script_path.exists():
            raise ResourceNotFoundError(
                f"The SimBu R script was not found at {self._r_script_path}."
            )

    def run(self, invocation: SimBuInvocation) -> SimBuRunResult:
        """Run one simulation synchronously and return its outcome."""
        self.assert_script_available()
        invocation.output_directory.mkdir(parents=True, exist_ok=True)

        process_environment = self._build_environment(invocation)
        command = [
            "Rscript",
            str(self._r_script_path),
            str(invocation.parameters.immune_cell_fraction),
            str(invocation.parameters.sample_count),
        ]

        _logger.info(
            "Starting SimBu: sample=%s fraction=%s n=%s",
            invocation.parameters.sample_base_name,
            invocation.parameters.immune_cell_fraction,
            invocation.parameters.sample_count,
        )

        try:
            completed_process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=process_environment,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return SimBuRunResult(
                succeeded=False,
                return_code=-1,
                standard_output="",
                standard_error=(
                    f"SimBu did not finish within {self._timeout_seconds} seconds."
                ),
            )
        except FileNotFoundError as error:
            return SimBuRunResult(
                succeeded=False,
                return_code=-1,
                standard_output="",
                standard_error=f"'Rscript' is not available on this machine: {error}",
            )

        standard_output = completed_process.stdout or ""
        standard_error = completed_process.stderr or ""
        plot_path, counts_path = SimBuRunResult.parse_emitted_paths(standard_output)

        return SimBuRunResult(
            succeeded=completed_process.returncode == 0,
            return_code=completed_process.returncode,
            standard_output=standard_output,
            standard_error=standard_error,
            plot_relative_path=plot_path,
            counts_relative_path=counts_path,
        )

    def _build_environment(self, invocation: SimBuInvocation) -> dict:
        process_environment = os.environ.copy()
        process_environment["SIMBU_BASE_PATH"] = self._as_directory_prefix(
            invocation.input_directory
        )
        process_environment["SIMBU_OUTPUT_DIR"] = self._as_directory_prefix(
            invocation.output_directory
        )
        process_environment["SIMBU_SAMPLE_NAME"] = invocation.parameters.sample_base_name
        process_environment["SIMBU_IMMUNE_FRACTION"] = str(
            invocation.parameters.immune_cell_fraction
        )
        return process_environment

    @staticmethod
    def _as_directory_prefix(directory: Path) -> str:
        """The R script concatenates strings, so it needs a trailing slash."""
        return str(directory).rstrip("/") + "/"


def find_optional_path(candidate: Optional[str]) -> Optional[Path]:
    """Helper for turning an emitted path string into a :class:`Path`."""
    return Path(candidate) if candidate else None
