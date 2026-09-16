"""Dataset preparation for the AI suite.

All pandas/numpy work of the former ``module5.py`` lives here, separated from
job orchestration and from H2O so that each part can be tested on its own.
"""
from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..domain.errors import ValidationError

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps pandas out of import time
    import pandas

_logger = logging.getLogger(__name__)

LABEL_COLUMN = "Label"
SAMPLE_FILE_PATTERN = "*.txt"


@dataclass(frozen=True)
class PreparedDatasets:
    """Scaled train/test matrices written to disk, ready for H2O."""

    train_file: Path
    test_file: Path
    shared_feature_count: int


class AiSuiteDatasetPreparer:
    """Merges the uploaded sample files, aligns and scales them."""

    def prepare(
        self, *, train_directory: Path, test_directory: Path, output_directory: Path
    ) -> PreparedDatasets:
        merged_train = self.merge_sample_directory(train_directory)
        merged_test = self.merge_sample_directory(test_directory)

        shared_columns = merged_test.columns.intersection(merged_train.columns)
        if len(shared_columns) == 0:
            raise ValidationError(
                "The train and test files share no common gene columns."
            )
        if LABEL_COLUMN not in shared_columns:
            raise ValidationError(
                f"The '{LABEL_COLUMN}' column is missing from train or test data."
            )

        scaled_train = self.min_max_scale(merged_train[shared_columns])
        scaled_test = self.min_max_scale(merged_test[shared_columns])

        output_directory.mkdir(parents=True, exist_ok=True)
        train_file = output_directory / "train_scaled.tsv"
        test_file = output_directory / "test_scaled.tsv"
        scaled_train.to_csv(train_file, sep="\t")
        scaled_test.to_csv(test_file, sep="\t")

        del merged_train, merged_test, scaled_train, scaled_test
        gc.collect()

        return PreparedDatasets(
            train_file=train_file,
            test_file=test_file,
            shared_feature_count=len(shared_columns) - 1,  # minus the label column
        )

    # -- merging -----------------------------------------------------------

    def merge_sample_directory(self, directory: Path) -> "pandas.DataFrame":
        """Concatenate every ``*.txt`` sample file below ``directory``."""
        import pandas as pandas_module

        if not directory.is_dir():
            raise ValidationError(f"The folder '{directory.name}' does not exist.")

        sample_files = sorted(directory.rglob(SAMPLE_FILE_PATTERN))
        if not sample_files:
            raise ValidationError(
                f"The folder '{directory.name}' contains no .txt sample files."
            )

        frames = [self.read_sample_file(sample_file) for sample_file in sample_files]
        merged = pandas_module.concat(frames, axis=0)

        del frames
        gc.collect()
        return merged

    @staticmethod
    def read_sample_file(sample_file: Path) -> "pandas.DataFrame":
        """Read one SimBu output file; its label is encoded in the file name.

        ``simbu_icf_0.02.txt`` therefore yields a ``Label`` column of ``0.02``.
        """
        import pandas as pandas_module

        raw_label = sample_file.stem.split("_")[-1]
        try:
            label_value = float(raw_label)
        except ValueError as error:
            raise ValidationError(
                f"Cannot read a label from the file name '{sample_file.name}'. "
                f"Expected a trailing number, for example 'simbu_icf_0.02.txt'."
            ) from error

        table = pandas_module.read_csv(
            sample_file, delimiter="\t", header=0, index_col=0
        ).transpose()
        table[LABEL_COLUMN] = label_value
        return table

    # -- transformations ---------------------------------------------------

    @staticmethod
    def min_max_scale(table: "pandas.DataFrame") -> "pandas.DataFrame":
        """Scale every feature column into [0, 1]; constant columns become 0."""
        import numpy as numpy_module

        scaled = table.copy()
        for column_name in scaled.columns:
            if column_name == LABEL_COLUMN:
                continue
            column_minimum = scaled[column_name].min()
            column_maximum = scaled[column_name].max()
            column_range = column_maximum - column_minimum
            if column_range == 0:
                scaled[column_name] = 0
            else:
                scaled[column_name] = (scaled[column_name] - column_minimum) / column_range

        return scaled.replace(
            [numpy_module.inf, -numpy_module.inf], numpy_module.nan
        ).fillna(0)

    @staticmethod
    def balance_by_downsampling(
        table: "pandas.DataFrame", label_column: str, random_seed: int
    ) -> "pandas.DataFrame":
        """Return an equal number of positive and negative rows, shuffled."""
        import pandas as pandas_module

        positive_rows = table[table[label_column] == 1]
        negative_rows = table[table[label_column] == 0]
        balanced_size = min(len(positive_rows), len(negative_rows))

        if balanced_size == 0:
            return table.iloc[0:0].copy()

        balanced = pandas_module.concat(
            [
                positive_rows.sample(n=balanced_size, random_state=random_seed),
                negative_rows.sample(n=balanced_size, random_state=random_seed),
            ],
            axis=0,
        )
        return balanced.sample(frac=1, random_state=random_seed).reset_index(drop=True)

    @staticmethod
    def clean_numeric_columns(table: "pandas.DataFrame") -> "pandas.DataFrame":
        """Coerce all feature columns to numbers and replace inf/NaN with 0."""
        import numpy as numpy_module
        import pandas as pandas_module

        feature_columns = [name for name in table.columns if name != LABEL_COLUMN]
        table[feature_columns] = table[feature_columns].apply(
            pandas_module.to_numeric, errors="coerce"
        )
        return table.replace(
            [numpy_module.inf, -numpy_module.inf], numpy_module.nan
        ).fillna(0)
