"""Parses the CSV/TSV file that defines a batch of SimBu runs.

Expected columns (header row required, case-insensitive):

``input_file``
    Base name of a ``.h5ad`` in the user's workspace, or a workspace-relative
    path.
``fractions``
    Semicolon separated list of immune-cell fractions, given either as ratios
    (``0.01;0.02``) or as percentages (``1;2``).
``n_samples``
    Number of synthetic samples per fraction.
``label`` *(optional)*
    Prefix for the output directories; defaults to the input base name.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Dict, List

from ..domain.errors import ValidationError
from ..domain.simbu import SimBuParameters

REQUIRED_COLUMNS = ("input_file", "fractions", "n_samples")
FRACTION_SEPARATORS = (";", ",")


@dataclass(frozen=True)
class BatchDefinitionRow:
    """One validated line of the batch definition file."""

    line_number: int
    input_reference: str
    immune_cell_fractions: List[float]
    sample_count: int
    label: str


class BatchDefinitionParser:
    """Turns raw CSV/TSV text into :class:`BatchDefinitionRow` objects."""

    def parse(self, raw_content: str) -> List[BatchDefinitionRow]:
        rows = self._read_rows(raw_content)
        if not rows:
            raise ValidationError("The batch file contains no data rows.")

        parsed_rows: List[BatchDefinitionRow] = []
        problems: List[str] = []

        for line_number, row in enumerate(rows, start=2):  # line 1 is the header
            try:
                parsed_rows.append(self._parse_single_row(line_number, row))
            except ValidationError as error:
                problems.append(f"Line {line_number}: {error.message}")

        if problems:
            raise ValidationError(
                "The batch file could not be read:\n" + "\n".join(problems)
            )
        return parsed_rows

    # -- internals ---------------------------------------------------------

    def _read_rows(self, raw_content: str) -> List[Dict[str, str]]:
        first_line = raw_content.splitlines()[0] if raw_content.strip() else ""
        delimiter = "\t" if "\t" in first_line else ","

        reader = csv.DictReader(io.StringIO(raw_content), delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValidationError("The batch file has no header row.")

        normalized_headers = {
            (name or "").strip().lower() for name in reader.fieldnames
        }
        missing_columns = [
            column for column in REQUIRED_COLUMNS if column not in normalized_headers
        ]
        if missing_columns:
            raise ValidationError(
                "The batch file is missing the column(s): "
                + ", ".join(missing_columns)
            )

        return [
            {
                (key or "").strip().lower(): (value or "").strip()
                for key, value in row.items()
            }
            for row in reader
            if any((value or "").strip() for value in row.values())
        ]

    def _parse_single_row(
        self, line_number: int, row: Dict[str, str]
    ) -> BatchDefinitionRow:
        input_reference = row.get("input_file", "")
        if not input_reference:
            raise ValidationError("'input_file' is empty.")

        raw_sample_count = row.get("n_samples", "")
        try:
            sample_count = int(raw_sample_count)
        except ValueError as error:
            raise ValidationError(
                f"'n_samples' is not a whole number ('{raw_sample_count}')."
            ) from error
        if sample_count < 1:
            raise ValidationError("'n_samples' must be at least 1.")

        fractions = self._parse_fractions(row.get("fractions", ""))

        return BatchDefinitionRow(
            line_number=line_number,
            input_reference=input_reference,
            immune_cell_fractions=fractions,
            sample_count=sample_count,
            label=row.get("label", "")
            or SimBuParameters.sanitize_sample_name(input_reference),
        )

    @staticmethod
    def _parse_fractions(raw_fractions: str) -> List[float]:
        if not raw_fractions:
            raise ValidationError("'fractions' is empty.")

        separator = ";" if ";" in raw_fractions else ","
        parts = [part.strip() for part in raw_fractions.split(separator) if part.strip()]
        if not parts:
            raise ValidationError("'fractions' contains no value.")

        fractions: List[float] = []
        for part in parts:
            try:
                fractions.append(SimBuParameters.normalize_fraction(float(part)))
            except ValueError as error:
                raise ValidationError(
                    f"'{part}' in 'fractions' is not a number."
                ) from error
        return fractions
