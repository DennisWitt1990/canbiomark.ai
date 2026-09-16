import type { HttpClient } from "./HttpClient";

export interface SimulationParameters {
    immuneCellFraction: number;
    sampleCount: number;
    sampleBaseName: string;
}

export interface SimulationResultPayload {
    succeeded: boolean;
    return_code: number;
    standard_output: string;
    standard_error: string;
    plot_path: string | null;
    counts_path: string | null;
    input_source: string | null;
    input_path: string | null;
    run_id: string | null;
}

/** The outcome of one SimBu run. */
export class SimulationResult {
    readonly succeeded: boolean;
    readonly returnCode: number;
    readonly standardOutput: string;
    readonly standardError: string;
    readonly plotPath: string | null;
    readonly countsPath: string | null;
    readonly inputSource: string | null;
    readonly inputPath: string | null;
    readonly runId: string | null;

    constructor(payload: SimulationResultPayload) {
        this.succeeded = payload.succeeded;
        this.returnCode = payload.return_code;
        this.standardOutput = payload.standard_output;
        this.standardError = payload.standard_error;
        this.plotPath = payload.plot_path;
        this.countsPath = payload.counts_path;
        this.inputSource = payload.input_source;
        this.inputPath = payload.input_path;
        this.runId = payload.run_id;
    }

    get hasDownloadableArtifacts(): boolean {
        return Boolean(this.plotPath || this.countsPath);
    }

    get inputSourceLabel(): string {
        if (this.inputSource === "upload") {
            return "uploaded file";
        }
        if (this.inputSource === "cell_selection") {
            return "cell selector output";
        }
        return "unknown source";
    }
}

export interface BatchTaskPayload {
    label: string;
    immune_cell_fraction: number;
    sample_count: number;
    status: string;
    error_message: string;
}

export interface BatchJobPayload {
    job_id: string;
    status: string;
    task_count: number;
    finished_task_count: number;
    failed_task_count: number;
    completed_percent: number;
    created_at: number;
    updated_at: number;
    tasks: BatchTaskPayload[];
}

/** A queued or finished batch of SimBu runs. */
export class BatchJob {
    readonly jobId: string;
    readonly status: string;
    readonly taskCount: number;
    readonly finishedTaskCount: number;
    readonly failedTaskCount: number;
    readonly completedPercent: number;
    readonly createdAt: Date;
    readonly updatedAt: Date;
    readonly tasks: BatchTaskPayload[];

    constructor(payload: BatchJobPayload) {
        this.jobId = payload.job_id;
        this.status = payload.status;
        this.taskCount = payload.task_count;
        this.finishedTaskCount = payload.finished_task_count;
        this.failedTaskCount = payload.failed_task_count;
        this.completedPercent = payload.completed_percent;
        this.createdAt = new Date(payload.created_at * 1000);
        this.updatedAt = new Date(payload.updated_at * 1000);
        this.tasks = payload.tasks;
    }

    get isRunning(): boolean {
        return this.status === "queued" || this.status === "running";
    }

    get hasDownloadableResults(): boolean {
        return this.status === "finished" || this.status === "finished_with_errors";
    }

    get shortId(): string {
        return this.jobId.slice(0, 8);
    }
}

/** Single runs and batch runs of the synthetic tissue generator. */
export class TissueGeneratorApi {
    constructor(private readonly httpClient: HttpClient) {}

    async uploadDataset(
        file: File,
        onProgressPercent?: (percent: number) => void,
    ): Promise<{ storedPath: string; sampleBaseName: string }> {
        const formData = new FormData();
        formData.append("file", file);

        const response = await this.httpClient.postFormData<{
            stored_path: string;
            sample_base_name: string;
        }>("/tissue-generator/upload", formData, onProgressPercent);

        return {
            storedPath: response.stored_path,
            sampleBaseName: response.sample_base_name,
        };
    }

    async runSimulation(parameters: SimulationParameters): Promise<SimulationResult> {
        const payload = await this.httpClient.post<SimulationResultPayload>(
            "/tissue-generator/run",
            {
                immune_cell_fraction: parameters.immuneCellFraction,
                sample_count: parameters.sampleCount,
                sample_base_name: parameters.sampleBaseName,
            },
        );
        return new SimulationResult(payload);
    }

    // --- batches ----------------------------------------------------------

    async uploadBatchDefinition(file: File): Promise<{
        definitionPath: string;
        rowCount: number;
        plannedTaskCount: number;
    }> {
        const formData = new FormData();
        formData.append("file", file);

        const response = await this.httpClient.postFormData<{
            definition_path: string;
            row_count: number;
            planned_task_count: number;
        }>("/tissue-batches/definitions", formData);

        return {
            definitionPath: response.definition_path,
            rowCount: response.row_count,
            plannedTaskCount: response.planned_task_count,
        };
    }

    async startBatch(definitionPath: string): Promise<BatchJob> {
        const payload = await this.httpClient.post<BatchJobPayload>(
            "/tissue-batches/jobs",
            { definition_path: definitionPath },
        );
        return new BatchJob(payload);
    }

    async listBatches(): Promise<BatchJob[]> {
        const payloads = await this.httpClient.get<BatchJobPayload[]>("/tissue-batches/jobs");
        return payloads.map((payload) => new BatchJob(payload));
    }

    async getBatch(jobId: string): Promise<BatchJob> {
        const payload = await this.httpClient.get<BatchJobPayload>(
            `/tissue-batches/jobs/${encodeURIComponent(jobId)}`,
        );
        return new BatchJob(payload);
    }

    async cancelBatch(jobId: string): Promise<void> {
        await this.httpClient.delete(`/tissue-batches/jobs/${encodeURIComponent(jobId)}`);
    }

    buildBatchArchiveUrl(jobId: string): string {
        return this.httpClient.buildUrl(
            `/tissue-batches/jobs/${encodeURIComponent(jobId)}/archive`,
        );
    }
}
