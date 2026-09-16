import type { HttpClient } from "./HttpClient";

/** Which kind of model the AI suite should fit. */
export const AnalysisTask = {
    Classification: "classification",
    Regression: "regression",
} as const;

export type AnalysisTaskName = (typeof AnalysisTask)[keyof typeof AnalysisTask];

export interface AiSuiteOption {
    value: string;
    display_name: string;
}

export interface AiSuiteOptions {
    tasks: AiSuiteOption[];
    regressionModels: AiSuiteOption[];
    classificationThresholds: number[];
}

export interface AiSuiteJobPayload {
    job_id: string;
    run_name: string;
    task: AnalysisTaskName;
    regression_models: string[];
    status: string;
    completed_fraction: number;
    completed_percent: number;
    message: string;
    error_message: string | null;
    created_at: number;
    updated_at: number;
}

/** One benchmarking run of the AI suite. */
export class AiSuiteJob {
    readonly jobId: string;
    readonly runName: string;
    readonly task: AnalysisTaskName;
    readonly regressionModels: string[];
    readonly status: string;
    readonly completedPercent: number;
    readonly message: string;
    readonly errorMessage: string | null;
    readonly createdAt: Date;

    constructor(payload: AiSuiteJobPayload) {
        this.jobId = payload.job_id;
        this.runName = payload.run_name;
        this.task = payload.task;
        this.regressionModels = payload.regression_models;
        this.status = payload.status;
        this.completedPercent = payload.completed_percent;
        this.message = payload.message;
        this.errorMessage = payload.error_message;
        this.createdAt = new Date(payload.created_at * 1000);
    }

    get isRunning(): boolean {
        return this.status === "queued" || this.status === "running";
    }

    get isFinished(): boolean {
        return this.status === "finished";
    }

    get hasFailed(): boolean {
        return this.status === "failed";
    }

    get isRegression(): boolean {
        return this.task === AnalysisTask.Regression;
    }

    get taskLabel(): string {
        return this.isRegression ? "Regression" : "Classification";
    }
}

export interface AiSuiteResults {
    jobId: string;
    status: string;
    resultsDirectory: string;
    files: string[];
    errorMessage: string | null;
}

export type DatasetSplit = "train" | "test";

/** Create, feed and run AI suite jobs. */
export class AiSuiteApi {
    constructor(private readonly httpClient: HttpClient) {}

    async fetchOptions(): Promise<AiSuiteOptions> {
        const response = await this.httpClient.get<{
            tasks: AiSuiteOption[];
            regression_models: AiSuiteOption[];
            classification_thresholds: number[];
        }>("/ai-suite/options");

        return {
            tasks: response.tasks,
            regressionModels: response.regression_models,
            classificationThresholds: response.classification_thresholds,
        };
    }

    async createJob(
        runName: string,
        task: AnalysisTaskName = AnalysisTask.Classification,
        regressionModels?: string[],
    ): Promise<AiSuiteJob> {
        const payload = await this.httpClient.post<AiSuiteJobPayload>("/ai-suite/jobs", {
            run_name: runName,
            task,
            regression_models: regressionModels ?? null,
        });
        return new AiSuiteJob(payload);
    }

    async uploadSplit(
        jobId: string,
        split: DatasetSplit,
        files: FileList | File[],
        onProgressPercent?: (percent: number) => void,
    ): Promise<number> {
        const formData = new FormData();
        formData.append("split", split);
        for (const file of Array.from(files)) {
            // Directory uploads carry their relative path in `webkitRelativePath`.
            const relativeName =
                (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
            formData.append("files", file, relativeName);
        }

        const response = await this.httpClient.postFormData<{ uploaded_file_count: number }>(
            `/ai-suite/jobs/${encodeURIComponent(jobId)}/uploads`,
            formData,
            onProgressPercent,
        );
        return response.uploaded_file_count;
    }

    async startRun(jobId: string): Promise<AiSuiteJob> {
        const payload = await this.httpClient.post<AiSuiteJobPayload>(
            `/ai-suite/jobs/${encodeURIComponent(jobId)}/run`,
        );
        return new AiSuiteJob(payload);
    }

    async getJob(jobId: string): Promise<AiSuiteJob> {
        const payload = await this.httpClient.get<AiSuiteJobPayload>(
            `/ai-suite/jobs/${encodeURIComponent(jobId)}`,
        );
        return new AiSuiteJob(payload);
    }

    async getResults(jobId: string): Promise<AiSuiteResults> {
        const response = await this.httpClient.get<{
            job_id: string;
            status: string;
            results_directory: string;
            files: string[];
            error_message: string | null;
        }>(`/ai-suite/jobs/${encodeURIComponent(jobId)}/results`);

        return {
            jobId: response.job_id,
            status: response.status,
            resultsDirectory: response.results_directory,
            files: response.files,
            errorMessage: response.error_message,
        };
    }
}
