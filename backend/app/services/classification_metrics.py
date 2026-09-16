"""Binary classification metrics derived from a confusion matrix."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class ConfusionMatrix:
    """The four counts of a binary confusion matrix."""

    true_negatives: int
    false_positives: int
    false_negatives: int
    true_positives: int

    @classmethod
    def from_h2o_table(cls, table_rows: Sequence[Sequence]) -> "ConfusionMatrix":
        """Build from the nested list H2O's ``confusion_matrix().to_list()`` returns."""
        return cls(
            true_negatives=int(table_rows[0][0]),
            false_positives=int(table_rows[0][1]),
            false_negatives=int(table_rows[1][0]),
            true_positives=int(table_rows[1][1]),
        )

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float:
        return float(numerator / denominator) if denominator else 0.0

    @property
    def sensitivity(self) -> float:
        """Also called recall or true-positive rate."""
        return self._ratio(self.true_positives, self.true_positives + self.false_negatives)

    @property
    def specificity(self) -> float:
        return self._ratio(self.true_negatives, self.true_negatives + self.false_positives)

    @property
    def precision(self) -> float:
        return self._ratio(self.true_positives, self.true_positives + self.false_positives)

    @property
    def f1_score(self) -> float:
        precision_plus_recall = self.precision + self.sensitivity
        if precision_plus_recall == 0:
            return 0.0
        return 2 * (self.precision * self.sensitivity) / precision_plus_recall


@dataclass(frozen=True)
class ThresholdEvaluation:
    """Everything reported for one binarisation threshold."""

    model_type: str
    threshold: float
    run_name: str
    area_under_curve: float
    confusion_matrix: ConfusionMatrix
    model_path: str = ""

    def to_report_row(self) -> Dict[str, object]:
        """Flat mapping for the Excel report."""
        return {
            "Model type": self.model_type,
            "Threshold": round(self.threshold, 4),
            "Run": self.run_name,
            "AUC": self.area_under_curve,
            "Sensitivity": self.confusion_matrix.sensitivity,
            "Specificity": self.confusion_matrix.specificity,
            "Precision": self.confusion_matrix.precision,
            "F1 Score": self.confusion_matrix.f1_score,
            "TN": self.confusion_matrix.true_negatives,
            "FP": self.confusion_matrix.false_positives,
            "FN": self.confusion_matrix.false_negatives,
            "TP": self.confusion_matrix.true_positives,
            "Model path": self.model_path,
        }


@dataclass(frozen=True)
class SkippedThreshold:
    """A threshold that could not be evaluated, with the reason why."""

    threshold: float
    reason: str

    def to_report_row(self) -> Dict[str, object]:
        return asdict(self)


def report_rows(evaluations: Sequence[ThresholdEvaluation]) -> List[Dict[str, object]]:
    return [evaluation.to_report_row() for evaluation in evaluations]


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegressionEvaluation:
    """Goodness-of-fit of one regression model on the test set."""

    model_type: str
    run_name: str
    mean_squared_error: float
    root_mean_squared_error: float
    mean_absolute_error: float
    r_squared: float
    predicted_sample_count: int
    model_path: str = ""

    def to_report_row(self) -> Dict[str, object]:
        """Flat mapping for the Excel report.

        The column names match the reference implementation of the thesis so
        that older result files stay comparable.
        """
        return {
            "Model type": self.model_type,
            "Run": self.run_name,
            "MSE": self.mean_squared_error,
            "RMSE": self.root_mean_squared_error,
            "MAE": self.mean_absolute_error,
            "R2": self.r_squared,
            "Samples": self.predicted_sample_count,
            "Model path": self.model_path,
        }


def regression_report_rows(
    evaluations: Sequence[RegressionEvaluation],
) -> List[Dict[str, object]]:
    return [evaluation.to_report_row() for evaluation in evaluations]
