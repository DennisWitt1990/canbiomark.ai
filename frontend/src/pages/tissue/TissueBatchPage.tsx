import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/ApiError";
import { apiRegistry } from "../../api/ApiRegistry";
import type { BatchJob } from "../../api/TissueGeneratorApi";
import Button from "../../components/Button";
import Card from "../../components/Card";
import ConfirmDialog from "../../components/ConfirmDialog";
import { Spinner } from "../../components/Spinner";
import StatusMessage from "../../components/StatusMessage";

const POLL_INTERVAL_MILLISECONDS = 4000;

const EXAMPLE_DEFINITION = `input_file,fractions,n_samples,label
tissue_a,0.01;0.02;0.05,500,tissueA
tissue_b,0.01;0.1;0.2,300,tissueB`;

/** Batch mode: upload a definition file and watch every simulation run. */
const TissueBatchPage: React.FC = () => {
    const [definitionFile, setDefinitionFile] = useState<File | null>(null);
    const [validatedDefinition, setValidatedDefinition] = useState<{
        definitionPath: string;
        rowCount: number;
        plannedTaskCount: number;
    } | null>(null);

    const [jobs, setJobs] = useState<BatchJob[]>([]);
    const [activeJob, setActiveJob] = useState<BatchJob | null>(null);
    const [jobToCancel, setJobToCancel] = useState<BatchJob | null>(null);

    const [isBusy, setIsBusy] = useState(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const pollTimerRef = useRef<number | null>(null);

    const loadJobs = useCallback(async () => {
        try {
            setJobs(await apiRegistry.tissueGenerator.listBatches());
        } catch (cause) {
            setErrorMessage(ApiError.from(cause, "The batches could not be loaded.").message);
        }
    }, []);

    useEffect(() => {
        void loadJobs();
    }, [loadJobs]);

    // Poll the selected job while it is still running.
    useEffect(() => {
        const stopPolling = () => {
            if (pollTimerRef.current !== null) {
                window.clearInterval(pollTimerRef.current);
                pollTimerRef.current = null;
            }
        };

        if (!activeJob?.isRunning) {
            stopPolling();
            return stopPolling;
        }

        pollTimerRef.current = window.setInterval(async () => {
            try {
                const refreshedJob = await apiRegistry.tissueGenerator.getBatch(activeJob.jobId);
                setActiveJob(refreshedJob);
                if (!refreshedJob.isRunning) {
                    void loadJobs();
                }
            } catch (cause) {
                // A deleted job stops the polling rather than spamming errors.
                if (ApiError.from(cause).statusCode === 404) {
                    setActiveJob(null);
                }
            }
        }, POLL_INTERVAL_MILLISECONDS);

        return stopPolling;
    }, [activeJob, loadJobs]);

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

    const handleValidateDefinition = () =>
        runGuarded(async () => {
            if (!definitionFile) {
                return;
            }
            setValidatedDefinition(
                await apiRegistry.tissueGenerator.uploadBatchDefinition(definitionFile),
            );
        }, "The batch file could not be validated.");

    const handleStartBatch = () =>
        runGuarded(async () => {
            if (!validatedDefinition) {
                return;
            }
            const startedJob = await apiRegistry.tissueGenerator.startBatch(
                validatedDefinition.definitionPath,
            );
            setActiveJob(startedJob);
            setValidatedDefinition(null);
            setDefinitionFile(null);
            await loadJobs();
        }, "The batch could not be started.");

    const handleCancelBatch = () =>
        runGuarded(async () => {
            if (!jobToCancel) {
                return;
            }
            await apiRegistry.tissueGenerator.cancelBatch(jobToCancel.jobId);
            if (activeJob?.jobId === jobToCancel.jobId) {
                setActiveJob(null);
            }
            setJobToCancel(null);
            await loadJobs();
        }, "The batch could not be cancelled.");

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex flex-col gap-1">
                    <h1 className="text-2xl font-bold text-black">Batch simulations</h1>
                    <p className="text-sm text-gray-600">
                        Runs many SimBu simulations in sequence from one definition file.
                    </p>
                </div>
                <Link
                    to="/tissue-generator"
                    className="text-sm font-medium underline hover:no-underline"
                >
                    ← Back to a single run
                </Link>
            </div>

            {errorMessage && <StatusMessage tone="error">{errorMessage}</StatusMessage>}

            <Card
                title="1. Upload the definition file"
                description="A .csv or .tsv file describing which dataset to simulate at which fractions."
            >
                <details className="text-sm">
                    <summary className="cursor-pointer font-medium">
                        Show the expected format
                    </summary>
                    <div className="pt-2 flex flex-col gap-2">
                        <p className="text-gray-600">
                            Required columns: <code>input_file</code>, <code>fractions</code>,{" "}
                            <code>n_samples</code>. Optional: <code>label</code>. Fractions are
                            separated by semicolons and may be ratios (0.02) or percentages (2).
                            Every referenced dataset must already exist in your workspace — upload
                            it in the single-run view first.
                        </p>
                        <pre className="bg-gray-50 border border-gray-200 rounded p-3 text-xs overflow-x-auto">
                            {EXAMPLE_DEFINITION}
                        </pre>
                    </div>
                </details>

                <input
                    type="file"
                    accept=".csv,.tsv"
                    disabled={isBusy}
                    onChange={(event) => {
                        setDefinitionFile(event.target.files?.[0] ?? null);
                        setValidatedDefinition(null);
                    }}
                    className="border border-gray-300 rounded px-3 py-2 text-sm"
                />

                <Button
                    variant="secondary"
                    className="h-10 px-4 justify-center w-fit"
                    onClick={handleValidateDefinition}
                    disabled={!definitionFile || isBusy}
                >
                    Validate the file
                </Button>

                {validatedDefinition && (
                    <StatusMessage tone="success">
                        {validatedDefinition.rowCount} row(s) read —{" "}
                        {validatedDefinition.plannedTaskCount} simulation(s) will run.
                    </StatusMessage>
                )}
            </Card>

            <Card
                title="2. Start the batch"
                description="Simulations run one after another in the background; you can leave this page."
            >
                <Button
                    variant="primary"
                    className="h-11 px-4 justify-center w-fit"
                    onClick={handleStartBatch}
                    disabled={!validatedDefinition || isBusy}
                >
                    Start the batch
                </Button>
            </Card>

            {activeJob && (
                <Card
                    title={`Batch ${activeJob.shortId}`}
                    description={`Status: ${activeJob.status} · ${activeJob.finishedTaskCount} of ${activeJob.taskCount} done`}
                    actions={
                        activeJob.hasDownloadableResults ? (
                            <a
                                href={apiRegistry.tissueGenerator.buildBatchArchiveUrl(
                                    activeJob.jobId,
                                )}
                                className="px-3 py-2 rounded-md border-2 border-black bg-white text-sm hover:bg-gray-50"
                            >
                                Download all results
                            </a>
                        ) : undefined
                    }
                >
                    <div className="flex items-center gap-3">
                        <div className="h-2 flex-1 bg-gray-200 rounded">
                            <div
                                className="h-2 bg-black rounded transition-all"
                                style={{ width: `${activeJob.completedPercent}%` }}
                            />
                        </div>
                        <span className="text-sm text-gray-600 whitespace-nowrap">
                            {activeJob.completedPercent}%
                        </span>
                        {activeJob.isRunning && <Spinner className="h-5 w-5" />}
                    </div>

                    {activeJob.failedTaskCount > 0 && (
                        <StatusMessage tone="warning">
                            {activeJob.failedTaskCount} simulation(s) failed. The details are below
                            and in the manifest inside the archive.
                        </StatusMessage>
                    )}

                    <div className="overflow-x-auto max-h-96 overflow-y-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-left text-gray-500 border-b border-gray-200">
                                    <th className="py-2 pr-3 font-medium">Label</th>
                                    <th className="py-2 pr-3 font-medium">Fraction</th>
                                    <th className="py-2 pr-3 font-medium">Samples</th>
                                    <th className="py-2 pr-3 font-medium">Status</th>
                                    <th className="py-2 font-medium">Error</th>
                                </tr>
                            </thead>
                            <tbody>
                                {activeJob.tasks.map((task) => (
                                    <tr key={task.label} className="border-b border-gray-100">
                                        <td className="py-2 pr-3 font-mono text-xs">{task.label}</td>
                                        <td className="py-2 pr-3">{task.immune_cell_fraction}</td>
                                        <td className="py-2 pr-3">{task.sample_count}</td>
                                        <td className="py-2 pr-3">
                                            <TaskStatusBadge status={task.status} />
                                        </td>
                                        <td className="py-2 text-xs text-red-700 break-all">
                                            {task.error_message || "—"}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </Card>
            )}

            <Card
                title="Your batches"
                actions={
                    <Button
                        variant="secondary"
                        className="h-9 px-3"
                        onClick={loadJobs}
                        disabled={isBusy}
                    >
                        Refresh
                    </Button>
                }
            >
                {jobs.length === 0 ? (
                    <p className="text-sm text-gray-600">No batch has been started yet.</p>
                ) : (
                    <ul className="flex flex-col gap-2">
                        {jobs.map((job) => (
                            <li
                                key={job.jobId}
                                className="flex items-center justify-between gap-3 border border-gray-200 rounded px-3 py-2 text-sm flex-wrap"
                            >
                                <div className="flex flex-col">
                                    <span className="font-mono text-xs">{job.shortId}</span>
                                    <span className="text-gray-600">
                                        {job.createdAt.toLocaleString()} · {job.taskCount} task(s) ·{" "}
                                        {job.status}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Button
                                        variant="secondary"
                                        className="h-9 px-3"
                                        onClick={async () =>
                                            setActiveJob(
                                                await apiRegistry.tissueGenerator.getBatch(job.jobId),
                                            )
                                        }
                                    >
                                        Show
                                    </Button>
                                    <Button
                                        variant="danger"
                                        className="h-9 px-3"
                                        onClick={() => setJobToCancel(job)}
                                    >
                                        {job.isRunning ? "Cancel" : "Delete"}
                                    </Button>
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
            </Card>

            {jobToCancel && (
                <ConfirmDialog
                    title={jobToCancel.isRunning ? "Cancel this batch?" : "Delete this batch?"}
                    isDestructive
                    busy={isBusy}
                    confirmLabel={jobToCancel.isRunning ? "Cancel the batch" : "Delete"}
                    message={
                        <>
                            Batch <strong>{jobToCancel.shortId}</strong> and all of its results are
                            removed from disk. This cannot be undone — download the archive first
                            if you still need the data.
                        </>
                    }
                    onConfirm={handleCancelBatch}
                    onCancel={() => setJobToCancel(null)}
                />
            )}
        </div>
    );
};

const TaskStatusBadge: React.FC<{ status: string }> = ({ status }) => {
    const toneClassName = ((): string => {
        switch (status) {
            case "finished":
                return "bg-emerald-50 text-emerald-700 border-emerald-200";
            case "failed":
                return "bg-red-50 text-red-700 border-red-200";
            case "running":
                return "bg-blue-50 text-blue-700 border-blue-200";
            case "cancelled":
                return "bg-amber-50 text-amber-800 border-amber-200";
            default:
                return "bg-gray-50 text-gray-700 border-gray-200";
        }
    })();

    return (
        <span className={`text-xs px-2 py-1 rounded-full border ${toneClassName}`}>{status}</span>
    );
};

export default TissueBatchPage;
