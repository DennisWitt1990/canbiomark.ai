import React, { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import {
    AnalysisTask,
    type AiSuiteJob,
    type AiSuiteOptions,
    type AiSuiteResults,
    type AnalysisTaskName,
    type DatasetSplit,
} from "../../api/AiSuiteApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import { Spinner } from "../../components/Spinner";
import StatusMessage from "../../components/StatusMessage";
import TextField from "../../components/TextField";

const POLL_INTERVAL_MILLISECONDS = 4000;

interface SplitUploadState {
    files: FileList | null;
    uploadedFileCount: number;
    progressPercent: number;
    isUploading: boolean;
}

const EMPTY_SPLIT_STATE: SplitUploadState = {
    files: null,
    uploadedFileCount: 0,
    progressPercent: 0,
    isUploading: false,
};

/** Create a job, upload the train and test folders, run the benchmark. */
const AiSuitePage: React.FC = () => {
    const [runName, setRunName] = useState("run_001");
    const [task, setTask] = useState<AnalysisTaskName>(AnalysisTask.Classification);
    const [options, setOptions] = useState<AiSuiteOptions | null>(null);
    const [selectedRegressionModels, setSelectedRegressionModels] = useState<string[]>([]);
    const [job, setJob] = useState<AiSuiteJob | null>(null);
    const [results, setResults] = useState<AiSuiteResults | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [isBusy, setIsBusy] = useState(false);

    const [trainUpload, setTrainUpload] = useState<SplitUploadState>(EMPTY_SPLIT_STATE);
    const [testUpload, setTestUpload] = useState<SplitUploadState>(EMPTY_SPLIT_STATE);

    const pollTimerRef = useRef<number | null>(null);

    const loadResults = useCallback(async (jobId: string) => {
        try {
            setResults(await apiRegistry.aiSuite.getResults(jobId));
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The results could not be loaded.").message);
        }
    }, []);

    useEffect(() => {
        apiRegistry.aiSuite
            .fetchOptions()
            .then((loadedOptions) => {
                setOptions(loadedOptions);
                setSelectedRegressionModels(
                    loadedOptions.regressionModels.map((model) => model.value),
                );
            })
            .catch(() => setOptions(null));
    }, []);

    // Poll while the pipeline is running.
    useEffect(() => {
        const stopPolling = () => {
            if (pollTimerRef.current !== null) {
                window.clearInterval(pollTimerRef.current);
                pollTimerRef.current = null;
            }
        };

        if (!job?.isRunning) {
            stopPolling();
            return stopPolling;
        }

        pollTimerRef.current = window.setInterval(async () => {
            try {
                const refreshedJob = await apiRegistry.aiSuite.getJob(job.jobId);
                setJob(refreshedJob);
                if (refreshedJob.isFinished) {
                    await loadResults(refreshedJob.jobId);
                }
            } catch (cause) {
                setErrorMessage(ApiError.from(cause, "The status could not be read.").message);
            }
        }, POLL_INTERVAL_MILLISECONDS);

        return stopPolling;
    }, [job, loadResults]);

    const runGuarded = async (action: () => Promise<void>, failureMessage: string) => {
        setIsBusy(true);
        setErrorMessage(null);
        try {
            await action();
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, failureMessage).message);
        } finally {
            setIsBusy(false);
        }
    };

    const handleCreateJob = () =>
        runGuarded(async () => {
            setJob(
                await apiRegistry.aiSuite.createJob(
                    runName.trim(),
                    task,
                    task === AnalysisTask.Regression ? selectedRegressionModels : undefined,
                ),
            );
            setResults(null);
            setTrainUpload(EMPTY_SPLIT_STATE);
            setTestUpload(EMPTY_SPLIT_STATE);
        }, "The job could not be created.");

    const handleUploadSplit = (split: DatasetSplit) => {
        const uploadState = split === "train" ? trainUpload : testUpload;
        const setUploadState = split === "train" ? setTrainUpload : setTestUpload;

        return runGuarded(async () => {
            if (!job || !uploadState.files) {
                return;
            }

            setUploadState({ ...uploadState, isUploading: true, progressPercent: 0 });
            const uploadedFileCount = await apiRegistry.aiSuite.uploadSplit(
                job.jobId,
                split,
                uploadState.files,
                (percent) =>
                    setUploadState((previous) => ({ ...previous, progressPercent: percent })),
            );
            setUploadState({
                files: uploadState.files,
                uploadedFileCount,
                progressPercent: 100,
                isUploading: false,
            });
        }, `The ${split} folder could not be uploaded.`);
    };

    const handleStartRun = () =>
        runGuarded(async () => {
            if (!job) {
                return;
            }
            setJob(await apiRegistry.aiSuite.startRun(job.jobId));
        }, "The run could not be started.");

    const handleReset = () => {
        setJob(null);
        setResults(null);
        setErrorMessage(null);
        setTrainUpload(EMPTY_SPLIT_STATE);
        setTestUpload(EMPTY_SPLIT_STATE);
    };

    const isRegression = task === AnalysisTask.Regression;
    const canCreateJob =
        runName.trim().length > 0 &&
        !job &&
        !isBusy &&
        (!isRegression || selectedRegressionModels.length > 0);

    const toggleRegressionModel = (modelValue: string) =>
        setSelectedRegressionModels((previous) =>
            previous.includes(modelValue)
                ? previous.filter((value) => value !== modelValue)
                : [...previous, modelValue],
        );

    const canStartRun =
        Boolean(job) &&
        trainUpload.uploadedFileCount > 0 &&
        testUpload.uploadedFileCount > 0 &&
        !job?.isRunning &&
        !isBusy;

    return (
        <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-bold text-black">AI suite</h1>
                <p className="text-sm text-gray-600">
                    Benchmarks H2O models on your synthetic tissues. Classification asks
                    whether the infiltration is above a threshold; regression predicts the
                    fraction itself.
                </p>
            </div>

            {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

            <Card title="1. Create a job" className="max-w-2xl">
                <TextField
                    label="Run name"
                    value={runName}
                    onChange={setRunName}
                    placeholder="run_001"
                    disabled={Boolean(job)}
                    hint="Appears in the Excel report so you can tell runs apart."
                />
                <fieldset className="border border-gray-200 rounded p-3 flex flex-col gap-3">
                    <legend className="text-sm font-medium px-1">What to fit</legend>

                    <label className="flex items-start gap-2 text-sm">
                        <input
                            type="radio"
                            className="mt-1"
                            checked={!isRegression}
                            disabled={Boolean(job)}
                            onChange={() => setTask(AnalysisTask.Classification)}
                        />
                        <span>
                            <span className="font-medium">Classification</span> — one deep
                            learning model per threshold, reporting AUC, sensitivity and
                            specificity.
                            {options && (
                                <span className="block text-xs text-gray-500">
                                    Thresholds:{" "}
                                    {options.classificationThresholds.join(", ")}
                                </span>
                            )}
                        </span>
                    </label>

                    <label className="flex items-start gap-2 text-sm">
                        <input
                            type="radio"
                            className="mt-1"
                            checked={isRegression}
                            disabled={Boolean(job)}
                            onChange={() => setTask(AnalysisTask.Regression)}
                        />
                        <span>
                            <span className="font-medium">Regression</span> — predicts the
                            immune cell fraction directly, reporting MSE, RMSE, MAE and R².
                            No thresholds involved.
                        </span>
                    </label>

                    {isRegression && options && (
                        <div className="pl-6 flex flex-col gap-2">
                            <span className="text-xs font-medium text-gray-700">
                                Estimators to fit
                            </span>
                            {options.regressionModels.map((model) => (
                                <label
                                    key={model.value}
                                    className="flex items-center gap-2 text-sm"
                                >
                                    <input
                                        type="checkbox"
                                        checked={selectedRegressionModels.includes(model.value)}
                                        disabled={Boolean(job)}
                                        onChange={() => toggleRegressionModel(model.value)}
                                    />
                                    {model.display_name}
                                </label>
                            ))}
                            {selectedRegressionModels.length === 0 && (
                                <span className="text-xs text-red-700">
                                    Select at least one estimator.
                                </span>
                            )}
                        </div>
                    )}
                </fieldset>

                <div className="flex items-center gap-3 flex-wrap">
                    <Button
                        variant="primary"
                        className="h-10 px-4 justify-center"
                        onClick={handleCreateJob}
                        disabled={!canCreateJob}
                    >
                        Create the job
                    </Button>
                    <Button
                        variant="secondary"
                        className="h-10 px-4 justify-center"
                        onClick={handleReset}
                        disabled={!job || job.isRunning}
                    >
                        Start over
                    </Button>
                    {job && (
                        <span className="text-xs text-gray-600">
                            {job.taskLabel} job:{" "}
                            <span className="font-mono">{job.jobId}</span>
                        </span>
                    )}
                </div>
            </Card>

            <Card
                title="2. Upload the data"
                description="Select the folder of SimBu .txt files for each split. The label is read from each file name, e.g. simbu_icf_0.02.txt."
            >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <SplitUploadPanel
                        title="Train folder"
                        uploadState={trainUpload}
                        disabled={!job || job.isRunning || isBusy}
                        onFilesSelected={(files) =>
                            setTrainUpload({ ...EMPTY_SPLIT_STATE, files })
                        }
                        onUpload={() => void handleUploadSplit("train")}
                    />
                    <SplitUploadPanel
                        title="Test folder"
                        uploadState={testUpload}
                        disabled={!job || job.isRunning || isBusy}
                        onFilesSelected={(files) => setTestUpload({ ...EMPTY_SPLIT_STATE, files })}
                        onUpload={() => void handleUploadSplit("test")}
                    />
                </div>
            </Card>

            <Card title="3. Run the benchmark">
                <Button
                    variant="primary"
                    className="h-11 px-4 justify-center w-fit"
                    onClick={handleStartRun}
                    disabled={!canStartRun}
                >
                    Start the AI suite
                </Button>

                {job && job.isRunning && (
                    <div className="flex flex-col gap-2">
                        <div className="h-2 w-full bg-gray-200 rounded">
                            <div
                                className="h-2 bg-black rounded transition-all"
                                style={{ width: `${job.completedPercent}%` }}
                            />
                        </div>
                        <div className="flex items-center gap-2 text-sm text-gray-600">
                            <Spinner className="h-5 w-5" />
                            {job.completedPercent}% — {job.message || "working ..."}
                        </div>
                        <p className="text-xs text-gray-500">
                            Training runs in the background and can take several minutes per
                            threshold.
                        </p>
                    </div>
                )}

                {job?.hasFailed && (
                    <StatusMessage tone="error">
                        {job.errorMessage ?? "The run failed."}
                    </StatusMessage>
                )}

                {job?.isFinished && (
                    <StatusMessage tone="success">The run finished successfully.</StatusMessage>
                )}
            </Card>

            <Card
                title="Results"
                actions={
                    <Button
                        variant="secondary"
                        className="h-9 px-3"
                        onClick={() => job && void loadResults(job.jobId)}
                        disabled={!job}
                    >
                        Refresh
                    </Button>
                }
            >
                {!results || results.files.length === 0 ? (
                    <p className="text-sm text-gray-600">
                        No result files yet. They appear once the run has finished.
                    </p>
                ) : (
                    <>
                        <p className="text-xs text-gray-500">
                            Directory: <span className="font-mono">{results.resultsDirectory}</span>
                        </p>
                        <div className="border border-gray-200 rounded p-2 max-h-96 overflow-auto flex flex-col gap-1">
                            {results.files.map((fileName) => (
                                <div
                                    key={fileName}
                                    className="flex items-center justify-between gap-3 px-2 py-1 rounded hover:bg-gray-50"
                                >
                                    <span className="text-sm font-mono break-all">{fileName}</span>
                                    <a
                                        href={apiRegistry.workspace.buildDownloadUrl(
                                            `${results.resultsDirectory}/${fileName}`,
                                        )}
                                        className="text-sm underline hover:no-underline whitespace-nowrap"
                                    >
                                        Download
                                    </a>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </Card>
        </div>
    );
};

interface SplitUploadPanelProps {
    title: string;
    uploadState: SplitUploadState;
    disabled: boolean;
    onFilesSelected: (files: FileList | null) => void;
    onUpload: () => void;
}

const SplitUploadPanel: React.FC<SplitUploadPanelProps> = ({
    title,
    uploadState,
    disabled,
    onFilesSelected,
    onUpload,
}) => (
    <div className="border border-gray-200 rounded p-3 flex flex-col gap-2">
        <div className="text-sm font-medium">{title}</div>
        <input
            type="file"
            multiple
            // `webkitdirectory` enables folder selection; it is not in the TS DOM types.
            {...({ webkitdirectory: "true" } as Record<string, string>)}
            disabled={disabled}
            onChange={(event) => onFilesSelected(event.target.files)}
            className="text-sm"
        />
        <div className="text-xs text-gray-600">
            {uploadState.files
                ? `${uploadState.files.length} file(s) selected`
                : "No folder selected"}
            {uploadState.uploadedFileCount > 0 && (
                <span className="ml-2 text-emerald-700 font-semibold">
                    {uploadState.uploadedFileCount} uploaded
                </span>
            )}
        </div>

        {uploadState.isUploading && (
            <div className="h-2 w-full bg-gray-200 rounded">
                <div
                    className="h-2 bg-black rounded transition-all"
                    style={{ width: `${uploadState.progressPercent}%` }}
                />
            </div>
        )}

        <Button
            variant="secondary"
            className="h-9 px-3 w-fit"
            onClick={onUpload}
            disabled={disabled || !uploadState.files || uploadState.isUploading}
        >
            {uploadState.isUploading ? "Uploading ..." : "Upload"}
        </Button>
    </div>
);

export default AiSuitePage;
