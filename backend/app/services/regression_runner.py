"""Regression benchmarking with H2O.

Where the classification runner binarises the label at a series of thresholds,
this runner predicts the immune-cell fraction **directly** as a continuous
value.  That answers a different question -- "how much infiltration is there?"
rather than "is it above 2 %?" -- and needs no thresholds at all.

Ported from the working implementation in the predecessor pipeline
(``MA_Extension/app/backend/app/ml/train.py::run_regression``), which is itself
the runnable version of the thesis appendix ``supplement_F_regression_h2o.py``.
The reported metric columns are kept identical so older result files stay
comparable.
"""
from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Sequence

from ..domain.analysis_task import RegressionModelKind
from ..domain.errors import ValidationError
from .ai_suite_dataset import LABEL_COLUMN, PreparedDatasets
from .classification_metrics import RegressionEvaluation
from .h2o_session import H2OSession

_logger = logging.getLogger(__name__)

ProgressReporter = Callable[[float, str], None]


@dataclass
class RegressionOutcome:
    """Everything one regression benchmark produced."""

    evaluations: List[RegressionEvaluation]
    prediction_rows: List[dict]


class RegressionRunner:
    """Trains one estimator per selected model kind and evaluates it."""

    def __init__(self, random_seed: int = 2008) -> None:
        self._random_seed = random_seed

    def run(
        self,
        *,
        session: H2OSession,
        prepared_datasets: PreparedDatasets,
        results_directory: Path,
        run_name: str,
        selected_models: Sequence[RegressionModelKind],
        report_progress: ProgressReporter,
    ) -> RegressionOutcome:
        import pandas

        if not selected_models:
            raise ValidationError("Select at least one regression model.")

        plots_directory = results_directory / "plots"
        models_directory = results_directory / "models"
        plots_directory.mkdir(parents=True, exist_ok=True)
        models_directory.mkdir(parents=True, exist_ok=True)

        train_table = pandas.read_csv(
            prepared_datasets.train_file, sep="\t", index_col=0
        )
        test_table = pandas.read_csv(prepared_datasets.test_file, sep="\t", index_col=0)
        predictor_columns = [
            name for name in train_table.columns if name != LABEL_COLUMN
        ]

        # The label stays numeric here -- uploading it as a factor would turn
        # the problem back into a classification.
        train_frame = session.upload(train_table)
        test_frame = session.upload(test_table)

        evaluations: List[RegressionEvaluation] = []
        prediction_rows: List[dict] = []

        try:
            for index, model_kind in enumerate(selected_models):
                report_progress(
                    0.15 + 0.70 * (index / len(selected_models)),
                    f"Training {model_kind.display_name} ...",
                )
                evaluation, predictions = self._train_and_evaluate(
                    session=session,
                    model_kind=model_kind,
                    predictor_columns=predictor_columns,
                    train_frame=train_frame,
                    test_frame=test_frame,
                    test_table=test_table,
                    run_name=run_name,
                    models_directory=models_directory,
                    plots_directory=plots_directory,
                )
                evaluations.append(evaluation)
                prediction_rows.extend(predictions)
        finally:
            session.release(train_frame, test_frame)
            del train_table, test_table
            gc.collect()

        return RegressionOutcome(
            evaluations=evaluations, prediction_rows=prediction_rows
        )

    # -- one model ---------------------------------------------------------

    def _train_and_evaluate(
        self,
        *,
        session: H2OSession,
        model_kind: RegressionModelKind,
        predictor_columns: List[str],
        train_frame,
        test_frame,
        test_table,
        run_name: str,
        models_directory: Path,
        plots_directory: Path,
    ) -> tuple[RegressionEvaluation, List[dict]]:
        import pandas

        model = self._build_estimator(model_kind)
        model.train(x=predictor_columns, y=LABEL_COLUMN, training_frame=train_frame)

        saved_model_path = session.save_model(
            model, models_directory / model_kind.estimator_class_name
        )
        performance = model.model_performance(test_frame)

        prediction_frame = model.predict(test_frame)
        predicted_values = prediction_frame.as_data_frame()["predict"].to_numpy()
        session.release(prediction_frame)

        comparison = pandas.DataFrame(
            {
                "Sample": test_table.index.astype(str).to_numpy(),
                "Actual": test_table[LABEL_COLUMN].to_numpy(),
                "Predicted": predicted_values,
            }
        )
        comparison["Delta"] = comparison["Predicted"] - comparison["Actual"]
        comparison["Model"] = model_kind.estimator_class_name

        self._write_actual_versus_predicted_plot(
            comparison,
            plots_directory
            / f"regression_{model_kind.value}_actual_vs_predicted.png",
            model_kind.display_name,
        )

        evaluation = RegressionEvaluation(
            model_type=model_kind.estimator_class_name,
            run_name=run_name,
            mean_squared_error=float(performance.mse()),
            root_mean_squared_error=float(performance.rmse()),
            mean_absolute_error=float(performance.mae()),
            r_squared=float(performance.r2()),
            predicted_sample_count=len(comparison),
            model_path=str(Path(saved_model_path).as_posix()),
        )
        prediction_rows = comparison.to_dict(orient="records")

        # Free the model inside the cluster before the next one is trained.
        session.release(model)
        del model, performance, comparison
        gc.collect()

        return evaluation, prediction_rows

    def _build_estimator(self, model_kind: RegressionModelKind):
        """Instantiate the H2O estimator for a model kind, seeded for repeatability."""
        from h2o.estimators.deeplearning import H2ODeepLearningEstimator
        from h2o.estimators.gbm import H2OGradientBoostingEstimator
        from h2o.estimators.glm import H2OGeneralizedLinearEstimator
        from h2o.estimators.random_forest import H2ORandomForestEstimator

        if model_kind is RegressionModelKind.DEEP_LEARNING:
            # reproducible=True pins the result at the cost of single-threaded
            # training; without it two runs on identical data differ.
            return H2ODeepLearningEstimator(seed=self._random_seed, reproducible=True)
        if model_kind is RegressionModelKind.GENERALIZED_LINEAR:
            return H2OGeneralizedLinearEstimator(seed=self._random_seed)
        if model_kind is RegressionModelKind.GRADIENT_BOOSTING:
            return H2OGradientBoostingEstimator(seed=self._random_seed)
        return H2ORandomForestEstimator(seed=self._random_seed)

    @staticmethod
    def _write_actual_versus_predicted_plot(
        comparison, target_file: Path, model_display_name: str
    ) -> None:
        """Scatter actual against predicted, ordered by the actual value."""
        import matplotlib

        matplotlib.use("Agg")  # no display inside the container
        import matplotlib.pyplot as pyplot

        ordered = comparison.sort_values(by="Actual").reset_index(drop=True)

        figure = pyplot.figure(figsize=(10, 6))
        pyplot.scatter(ordered.index, ordered["Actual"], label="Actual", s=18)
        pyplot.scatter(
            ordered.index, ordered["Predicted"], label="Predicted", s=18, alpha=0.5
        )
        pyplot.xlabel("Sample index (sorted by the actual value)")
        pyplot.ylabel("Immune cell fraction")
        pyplot.title(f"Actual versus predicted | {model_display_name}")
        pyplot.legend()
        pyplot.grid(True, alpha=0.3)
        pyplot.tight_layout()
        pyplot.savefig(target_file, dpi=120)
        pyplot.close(figure)
