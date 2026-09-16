"""The AI suite offers both a classification and a regression task."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.analysis_task import AnalysisTask, RegressionModelKind
from app.services.ai_suite_service import DEFAULT_THRESHOLDS
from app.services.classification_metrics import RegressionEvaluation, ConfusionMatrix


# --- the task enums ---------------------------------------------------------


def test_both_tasks_write_their_own_workbook() -> None:
    assert AnalysisTask.CLASSIFICATION.result_workbook_name == "results_classification.xlsx"
    assert AnalysisTask.REGRESSION.result_workbook_name == "results_regression.xlsx"


def test_four_regression_models_are_offered_by_default() -> None:
    assert len(RegressionModelKind.default_selection()) == 4
    assert {model.estimator_class_name for model in RegressionModelKind} == {
        "H2ODeepLearningEstimator",
        "H2OGeneralizedLinearEstimator",
        "H2OGradientBoostingEstimator",
        "H2ORandomForestEstimator",
    }


@pytest.mark.parametrize("raw", ["classification", "REGRESSION", " regression "])
def test_task_names_are_parsed_leniently(raw: str) -> None:
    assert AnalysisTask.parse(raw) in tuple(AnalysisTask)


def test_an_unknown_task_is_rejected() -> None:
    from app.domain.errors import ValidationError

    with pytest.raises(ValidationError):
        AnalysisTask.parse("clustering")


# --- the threshold list -----------------------------------------------------


def test_the_threshold_list_has_no_stray_zero() -> None:
    """Regression guard for the comma typo in the predecessor.

    ``[0.01, 0,.02, ...]`` silently parsed as ``[0.01, 0, 0.02, ...]``. A zero
    threshold binarises every label to 1, which either crashes H2O with
    "response cannot be constant" or trains a meaningless model.
    """
    assert 0 not in DEFAULT_THRESHOLDS
    assert all(threshold > 0 for threshold in DEFAULT_THRESHOLDS)
    assert len(DEFAULT_THRESHOLDS) == len(set(DEFAULT_THRESHOLDS))
    assert list(DEFAULT_THRESHOLDS) == sorted(DEFAULT_THRESHOLDS)


# --- regression metrics -----------------------------------------------------


def test_the_regression_report_row_keeps_the_thesis_column_names() -> None:
    row = RegressionEvaluation(
        model_type="H2OGradientBoostingEstimator",
        run_name="run_001",
        mean_squared_error=0.0004,
        root_mean_squared_error=0.02,
        mean_absolute_error=0.015,
        r_squared=0.87,
        predicted_sample_count=500,
    ).to_report_row()

    assert set(row) >= {"Model type", "Run", "MSE", "RMSE", "MAE", "R2"}
    assert row["R2"] == 0.87


# --- the API ----------------------------------------------------------------


def test_the_options_endpoint_lists_tasks_and_models(admin_client: TestClient) -> None:
    response = admin_client.get("/api/ai-suite/options")
    assert response.status_code == 200

    body = response.json()
    assert {task["value"] for task in body["tasks"]} == {"classification", "regression"}
    assert len(body["regression_models"]) == 4
    assert 0 not in body["classification_thresholds"]


def test_a_regression_job_records_its_task_and_models(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/ai-suite/jobs",
        json={
            "run_name": "regression_run",
            "task": "regression",
            "regression_models": ["gradient_boosting", "random_forest"],
        },
    )
    assert response.status_code == 201

    body = response.json()
    assert body["task"] == "regression"
    assert body["regression_models"] == ["gradient_boosting", "random_forest"]


def test_a_job_defaults_to_classification(admin_client: TestClient) -> None:
    response = admin_client.post("/api/ai-suite/jobs", json={"run_name": "default_run"})
    assert response.json()["task"] == "classification"


def test_an_unknown_regression_model_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/ai-suite/jobs",
        json={"run_name": "bad", "task": "regression", "regression_models": ["svm"]},
    )
    assert response.status_code == 400
    assert "svm" in response.json()["detail"]


def test_a_run_without_uploads_is_refused(admin_client: TestClient) -> None:
    job_id = admin_client.post(
        "/api/ai-suite/jobs", json={"run_name": "empty", "task": "regression"}
    ).json()["job_id"]

    response = admin_client.post(f"/api/ai-suite/jobs/{job_id}/run")
    assert response.status_code == 400
    assert "upload" in response.json()["detail"].lower()


def test_confusion_matrix_helpers_are_unaffected_by_the_new_task() -> None:
    matrix = ConfusionMatrix.from_h2o_table([[5, 1], [2, 8]])
    assert matrix.true_positives == 8
    assert matrix.sensitivity == pytest.approx(8 / 10)
