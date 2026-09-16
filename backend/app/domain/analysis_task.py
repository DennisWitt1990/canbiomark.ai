"""What kind of model the AI suite should fit."""
from __future__ import annotations

from enum import Enum
from typing import List

from .errors import ValidationError


class AnalysisTask(str, Enum):
    """Classification binarises the label; regression predicts it directly."""

    CLASSIFICATION = "classification"
    REGRESSION = "regression"

    @classmethod
    def parse(cls, raw_value: str) -> "AnalysisTask":
        normalized = (raw_value or "").strip().lower()
        for task in cls:
            if task.value == normalized:
                return task
        raise ValidationError(
            f"Unknown analysis task {raw_value!r}. Valid values: "
            + ", ".join(task.value for task in cls)
        )

    @property
    def result_workbook_name(self) -> str:
        return f"results_{self.value}.xlsx"


class RegressionModelKind(str, Enum):
    """The four H2O estimators used for regression.

    The set follows the reference implementation of the thesis (deep learning,
    a generalised linear model, gradient boosting and a random forest), which
    covers one non-linear network, one linear baseline and two tree ensembles.
    """

    DEEP_LEARNING = "deep_learning"
    GENERALIZED_LINEAR = "generalized_linear"
    GRADIENT_BOOSTING = "gradient_boosting"
    RANDOM_FOREST = "random_forest"

    @classmethod
    def parse(cls, raw_value: str) -> "RegressionModelKind":
        normalized = (raw_value or "").strip().lower()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValidationError(
            f"Unknown regression model {raw_value!r}. Valid values: "
            + ", ".join(kind.value for kind in cls)
        )

    @classmethod
    def default_selection(cls) -> List["RegressionModelKind"]:
        return list(cls)

    @property
    def estimator_class_name(self) -> str:
        """The H2O class name, reported in the result workbook."""
        return {
            RegressionModelKind.DEEP_LEARNING: "H2ODeepLearningEstimator",
            RegressionModelKind.GENERALIZED_LINEAR: "H2OGeneralizedLinearEstimator",
            RegressionModelKind.GRADIENT_BOOSTING: "H2OGradientBoostingEstimator",
            RegressionModelKind.RANDOM_FOREST: "H2ORandomForestEstimator",
        }[self]

    @property
    def display_name(self) -> str:
        return {
            RegressionModelKind.DEEP_LEARNING: "Deep learning",
            RegressionModelKind.GENERALIZED_LINEAR: "Generalised linear model",
            RegressionModelKind.GRADIENT_BOOSTING: "Gradient boosting",
            RegressionModelKind.RANDOM_FOREST: "Random forest",
        }[self]
