"""The AI suite (formerly "module 5").

A job owns an input folder (``train``/``test`` uploads) and a results folder.
Running it fits models on the uploaded synthetic tissues and writes plots plus
an Excel report. Two tasks are supported:

``classification``
    Binarises the immune-cell fraction at a series of thresholds and trains one
    deep-learning classifier per threshold. Answers "is the infiltration above
    2 %?" and reports AUC, sensitivity, specificity and so on.

``regression``
    Predicts the fraction directly as a continuous value with four estimators.
    Answers "how much infiltration is there?" and reports MSE, RMSE, MAE and R².

Both share the same uploads, the same preparation step and the same H2O cluster
handling, so switching task does not mean re-uploading anything.
"""
from __future__ import annotations

import gc
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, List, Optional, Sequence

from ..domain.analysis_task import AnalysisTask, RegressionModelKind
from ..domain.errors import ValidationError
from ..domain.job import JobProgress, JobStatus
from ..jobs.background_worker import BackgroundWorker
from ..jobs.job_registry import JobRegistry
from .ai_suite_dataset import (
    AiSuiteDatasetPreparer,
    LABEL_COLUMN,
    PreparedDatasets,
)
from .classification_metrics import (
    ConfusionMatrix,
    SkippedThreshold,
    ThresholdEvaluation,
    regression_report_rows,
    report_rows,
)
from .h2o_session import H2OSession
from .regression_runner import RegressionRunner
from .workspace_service import UserWorkspace

_logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS: Sequence[float] = (
    0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.1, 0.2,
)
RANDOM_SEED = 2008
CLASSIFIER_TYPE_NAME = "H2ODeepLearningEstimator"


@dataclass
class AiSuiteJob:
    """One AI-suite run owned by a single user."""

    job_id: str
    owner_user_id: str
    run_name: str
    input_directory: Path
    results_directory: Path
    task: AnalysisTask = AnalysisTask.CLASSIFICATION
    regression_models: List[RegressionModelKind] = field(
        default_factory=RegressionModelKind.default_selection
    )
    status: JobStatus = JobStatus.CREATED
    progress: JobProgress = field(default_factory=JobProgress)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error_message: Optional[str] = None
    result_files: List[str] = field(default_factory=list)

    @property
    def train_directory(self) -> Path:
        return self.input_directory / "train"

    @property
    def test_directory(self) -> Path:
        return self.input_directory / "test"

    def touch(self) -> None:
        self.updated_at = time.time()


class AiSuiteService:
    """Creates jobs, accepts uploads and runs the benchmarking pipeline."""

    def __init__(
        self,
        *,
        dataset_preparer: AiSuiteDatasetPreparer,
        job_registry: JobRegistry[AiSuiteJob],
        background_worker: BackgroundWorker,
        regression_runner: Optional[RegressionRunner] = None,
        h2o_max_memory: str = "20g",
        thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    ) -> None:
        self._dataset_preparer = dataset_preparer
        self._job_registry = job_registry
        self._background_worker = background_worker
        self._regression_runner = regression_runner or RegressionRunner(RANDOM_SEED)
        self._h2o_max_memory = h2o_max_memory
        self._thresholds = tuple(thresholds)

    @property
    def thresholds(self) -> tuple:
        """The binarisation thresholds used by the classification task."""
        return self._thresholds

    # -- job life cycle -----------------------------------------------------

    def create_job(
        self,
        workspace: UserWorkspace,
        run_name: str,
        task: AnalysisTask = AnalysisTask.CLASSIFICATION,
        regression_models: Optional[Sequence[RegressionModelKind]] = None,
    ) -> AiSuiteJob:
        sanitized_run_name = (run_name or "").strip() or "run"
        job_id = (
            f"ai_suite_{time.strftime('%Y-%m-%d_%H-%M-%S')}_{uuid.uuid4().hex[:8]}"
        )

        job_directory = workspace.ai_suite_directory / job_id
        input_directory = job_directory / "input"
        results_directory = job_directory / "results"
        (input_directory / "train").mkdir(parents=True, exist_ok=True)
        (input_directory / "test").mkdir(parents=True, exist_ok=True)
        results_directory.mkdir(parents=True, exist_ok=True)

        selected_models = list(
            regression_models or RegressionModelKind.default_selection()
        )
        if task is AnalysisTask.REGRESSION and not selected_models:
            raise ValidationError("Select at least one regression model.")

        job = AiSuiteJob(
            job_id=job_id,
            owner_user_id=workspace.user_id,
            run_name=sanitized_run_name,
            input_directory=input_directory,
            results_directory=results_directory,
            task=task,
            regression_models=selected_models,
            status=JobStatus.CREATED,
            progress=JobProgress(0.0, "Created; waiting for uploads."),
        )
        return self._job_registry.register(job)

    def get_job(self, workspace: UserWorkspace, job_id: str) -> AiSuiteJob:
        return self._job_registry.get_for_owner(job_id, workspace.user_id)

    def list_jobs(self, workspace: UserWorkspace) -> List[AiSuiteJob]:
        return self._job_registry.list_for_owner(
            workspace.user_id, sort_key=lambda job: job.created_at
        )

    # -- uploads -----------------------------------------------------------

    def store_uploaded_sample(
        self,
        workspace: UserWorkspace,
        job: AiSuiteJob,
        split_name: str,
        relative_file_name: str,
        file_stream: BinaryIO,
    ) -> Path:
        """Save one uploaded sample file into ``train`` or ``test``."""
        split_directory = self._resolve_split_directory(job, split_name)
        sanitized_name = UserWorkspace.sanitize_relative_path(relative_file_name)

        target_path = (split_directory / sanitized_name).resolve()
        workspace.assert_inside(target_path)
        if split_directory.resolve() not in target_path.parents:
            raise ValidationError("The upload path escapes the target folder.")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as target_file:
            shutil.copyfileobj(file_stream, target_file)
        return target_path

    def start_run(self, workspace: UserWorkspace, job: AiSuiteJob) -> AiSuiteJob:
        if not workspace.list_files_recursively(job.train_directory):
            raise ValidationError("Upload the train folder before starting the run.")
        if not workspace.list_files_recursively(job.test_directory):
            raise ValidationError("Upload the test folder before starting the run.")

        self._job_registry.update(
            job.job_id,
            status=JobStatus.QUEUED,
            progress=JobProgress(0.0, "Queued."),
            error_message=None,
        )
        self._background_worker.start(self._execute_run, job.job_id)
        return job

    def collect_result_files(
        self, workspace: UserWorkspace, job: AiSuiteJob
    ) -> List[str]:
        result_files = workspace.list_files_recursively(job.results_directory)
        self._job_registry.update(job.job_id, result_files=result_files)
        return result_files

    def results_relative_directory(
        self, workspace: UserWorkspace, job: AiSuiteJob
    ) -> str:
        return workspace.to_relative_path(job.results_directory)

    # -- the pipeline -------------------------------------------------------

    def _execute_run(self, job_id: str) -> None:
        job = self._job_registry.find(job_id)
        if job is None:
            return

        self._report(job_id, JobStatus.RUNNING, 0.02, "Merging the uploaded samples ...")

        try:
            prepared_datasets = self._dataset_preparer.prepare(
                train_directory=job.train_directory,
                test_directory=job.test_directory,
                output_directory=job.results_directory,
            )

            self._report(job_id, JobStatus.RUNNING, 0.12, "Starting H2O ...")
            # The session guarantees the cluster is stopped and its port is
            # released even when training raises, so a following job can start.
            with H2OSession(max_memory=self._h2o_max_memory) as session:
                session.remove_all()

                if job.task is AnalysisTask.REGRESSION:
                    self._run_regression(job_id, job, prepared_datasets, session)
                else:
                    self._run_classification(job_id, job, prepared_datasets, session)

            self._report(job_id, JobStatus.RUNNING, 0.98, "Collecting the results ...")
            result_files = sorted(
                str(entry.relative_to(job.results_directory))
                for entry in job.results_directory.rglob("*")
                if entry.is_file()
            )
            self._job_registry.update(
                job_id,
                status=JobStatus.FINISHED,
                progress=JobProgress(1.0, "Finished."),
                result_files=result_files,
            )

        except Exception as error:  # noqa: BLE001 - surfaced to the user as job state
            _logger.exception("AI suite job %s failed.", job_id)
            self._fail(job_id, str(error))
        finally:
            gc.collect()

    # -- regression --------------------------------------------------------

    def _run_regression(
        self,
        job_id: str,
        job: AiSuiteJob,
        prepared_datasets: PreparedDatasets,
        session: H2OSession,
    ) -> None:
        import pandas

        outcome = self._regression_runner.run(
            session=session,
            prepared_datasets=prepared_datasets,
            results_directory=job.results_directory,
            run_name=job.run_name,
            selected_models=job.regression_models,
            report_progress=lambda fraction, message: self._report(
                job_id, JobStatus.RUNNING, fraction, message
            ),
        )

        self._report(job_id, JobStatus.RUNNING, 0.90, "Writing the Excel report ...")
        workbook_path = job.results_directory / job.task.result_workbook_name
        with pandas.ExcelWriter(workbook_path, engine="openpyxl") as writer:
            pandas.DataFrame(regression_report_rows(outcome.evaluations)).to_excel(
                writer, sheet_name="Results", index=False
            )
            pandas.DataFrame(outcome.prediction_rows).to_excel(
                writer, sheet_name="Predictions", index=False
            )

    # -- classification ----------------------------------------------------

    def _run_classification(
        self,
        job_id: str,
        job: AiSuiteJob,
        prepared_datasets: PreparedDatasets,
        session: H2OSession,
    ) -> None:
        import pandas

        evaluations, downsampled_evaluations, skipped = self._train_all_thresholds(
            job_id, job, prepared_datasets, session
        )

        self._report(job_id, JobStatus.RUNNING, 0.90, "Writing the Excel report ...")
        workbook_path = job.results_directory / job.task.result_workbook_name
        with pandas.ExcelWriter(workbook_path, engine="openpyxl") as writer:
            pandas.DataFrame(report_rows(evaluations)).to_excel(
                writer, sheet_name="Results", index=False
            )
            pandas.DataFrame(report_rows(downsampled_evaluations)).to_excel(
                writer, sheet_name="Results_Downsampled", index=False
            )
            if skipped:
                # Documented explicitly, so skipped thresholds are never silent.
                pandas.DataFrame(
                    [item.to_report_row() for item in skipped]
                ).to_excel(writer, sheet_name="Skipped_Thresholds", index=False)

        if not evaluations:
            raise ValidationError(
                "Every threshold was skipped because the binarised label was "
                "constant in the train or test set. Check the label range of "
                "your samples against the configured thresholds, or use the "
                "regression task, which needs no thresholds."
            )

    def _train_all_thresholds(
        self,
        job_id: str,
        job: AiSuiteJob,
        prepared_datasets: PreparedDatasets,
        session: H2OSession,
    ) -> tuple[List[ThresholdEvaluation], List[ThresholdEvaluation], List[SkippedThreshold]]:
        import pandas
        from h2o.estimators.deeplearning import H2ODeepLearningEstimator

        train_table = pandas.read_csv(
            prepared_datasets.train_file, sep="\t", index_col=0
        )
        test_table = pandas.read_csv(prepared_datasets.test_file, sep="\t", index_col=0)
        predictor_columns = [
            name for name in train_table.columns if name != LABEL_COLUMN
        ]

        plots_directory = job.results_directory / "plots"
        models_directory = job.results_directory / "models"
        plots_directory.mkdir(parents=True, exist_ok=True)
        models_directory.mkdir(parents=True, exist_ok=True)

        evaluations: List[ThresholdEvaluation] = []
        downsampled_evaluations: List[ThresholdEvaluation] = []
        skipped_thresholds: List[SkippedThreshold] = []

        for index, threshold in enumerate(self._thresholds):
            self._report(
                job_id,
                JobStatus.RUNNING,
                0.15 + 0.70 * (index / max(len(self._thresholds), 1)),
                f"Training threshold {threshold:.2f} ...",
            )

            train_labels = (train_table[LABEL_COLUMN] >= threshold).astype(int)
            test_labels = (test_table[LABEL_COLUMN] >= threshold).astype(int)

            # H2O cannot fit a classifier when one side has a single class.
            if train_labels.nunique() < 2 or test_labels.nunique() < 2:
                skipped_thresholds.append(
                    SkippedThreshold(
                        threshold=threshold,
                        reason=(
                            "The binarised label is constant "
                            f"(train classes={train_labels.nunique()}, "
                            f"test classes={test_labels.nunique()})."
                        ),
                    )
                )
                continue

            binarized_train = self._dataset_preparer.clean_numeric_columns(
                train_table.assign(**{LABEL_COLUMN: train_labels})
            )
            binarized_test = self._dataset_preparer.clean_numeric_columns(
                test_table.assign(**{LABEL_COLUMN: test_labels})
            )

            train_frame = session.upload(binarized_train, (LABEL_COLUMN,))
            test_frame = session.upload(binarized_test, (LABEL_COLUMN,))

            model = H2ODeepLearningEstimator()
            model.train(
                x=predictor_columns, y=LABEL_COLUMN, training_frame=train_frame
            )

            saved_model_path = session.save_model(
                model, models_directory / f"deeplearning_thr_{threshold:.2f}"
            )

            performance = model.model_performance(test_frame)
            evaluations.append(
                ThresholdEvaluation(
                    model_type=CLASSIFIER_TYPE_NAME,
                    threshold=threshold,
                    run_name=job.run_name,
                    area_under_curve=float(performance.auc()),
                    confusion_matrix=ConfusionMatrix.from_h2o_table(
                        performance.confusion_matrix().to_list()
                    ),
                    model_path=str(Path(saved_model_path).as_posix()),
                )
            )

            self._write_roc_plot(
                performance, plots_directory / f"roc_thr_{threshold:.2f}.png", threshold
            )

            downsampled_evaluation = self._evaluate_on_balanced_subset(
                session, model, binarized_test, threshold, job.run_name
            )
            if downsampled_evaluation is not None:
                downsampled_evaluations.append(downsampled_evaluation)

            # Remove the frames and the model from the CLUSTER, not just from
            # Python: otherwise the JVM heap grows with every threshold until
            # the cluster spends its time collecting garbage.
            session.release(train_frame, test_frame, model)
            del binarized_train, binarized_test, model, performance
            gc.collect()

        return evaluations, downsampled_evaluations, skipped_thresholds

    def _evaluate_on_balanced_subset(
        self,
        session: H2OSession,
        model,
        binarized_test,
        threshold: float,
        run_name: str,
    ) -> Optional[ThresholdEvaluation]:
        """Re-evaluate on an equally sized positive/negative subsample."""
        balanced_test = self._dataset_preparer.balance_by_downsampling(
            binarized_test.copy(), LABEL_COLUMN, RANDOM_SEED
        )
        if len(balanced_test) == 0 or balanced_test[LABEL_COLUMN].nunique() < 2:
            return None

        balanced_frame = session.upload(balanced_test, (LABEL_COLUMN,))
        try:
            performance = model.model_performance(balanced_frame)
            return ThresholdEvaluation(
                model_type=CLASSIFIER_TYPE_NAME,
                threshold=threshold,
                run_name=run_name,
                area_under_curve=float(performance.auc()),
                confusion_matrix=ConfusionMatrix.from_h2o_table(
                    performance.confusion_matrix().to_list()
                ),
            )
        finally:
            session.release(balanced_frame)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _write_roc_plot(performance, target_file: Path, threshold: float) -> None:
        import matplotlib

        matplotlib.use("Agg")  # no display inside the container
        import matplotlib.pyplot as pyplot

        figure = pyplot.figure(figsize=(10, 6))
        pyplot.plot(performance.fprs, performance.tprs, linewidth=2)
        pyplot.plot([0, 1], [0, 1], linestyle="--")
        pyplot.xlim([0.0, 1.0])
        pyplot.ylim([0.0, 1.05])
        pyplot.xlabel("False positive rate (1 - specificity)")
        pyplot.ylabel("True positive rate (sensitivity)")
        pyplot.title(f"ROC | Deep learning | threshold = {threshold:.2f}")
        pyplot.grid(True)
        pyplot.tight_layout()
        pyplot.savefig(target_file)
        pyplot.close(figure)

    @staticmethod
    def _resolve_split_directory(job: AiSuiteJob, split_name: str) -> Path:
        normalized = (split_name or "").strip().lower()
        if normalized == "train":
            return job.train_directory
        if normalized == "test":
            return job.test_directory
        raise ValidationError("The split must be either 'train' or 'test'.")

    def _report(
        self, job_id: str, status: JobStatus, completed_fraction: float, message: str
    ) -> None:
        self._job_registry.update(
            job_id, status=status, progress=JobProgress(completed_fraction, message)
        )

    def _fail(self, job_id: str, error_message: str) -> None:
        self._job_registry.update(
            job_id,
            status=JobStatus.FAILED,
            progress=JobProgress(0.0, "Failed."),
            error_message=error_message,
        )
