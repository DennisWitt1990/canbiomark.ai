import type { HttpClient } from "./HttpClient";

/** The remote catalogues that can be searched. */
export const DatasetSource = {
    CellxGene: "cellxgene",
    EbiBioStudies: "ebi_biostudies",
} as const;

export type DatasetSourceName = (typeof DatasetSource)[keyof typeof DatasetSource];

export interface RemoteDatasetPayload {
    source: DatasetSourceName;
    dataset_id: string;
    title: string;
    collection_name: string;
    organisms: string[];
    tissues: string[];
    diseases: string[];
    assays: string[];
    cell_count: number | null;
    file_size_megabytes: number | null;
    publication_doi: string;
    landing_page_url: string;
    download_reference: string;
}

/** One dataset found online. */
export class RemoteDataset {
    readonly payload: RemoteDatasetPayload;

    constructor(payload: RemoteDatasetPayload) {
        this.payload = payload;
    }

    get datasetId(): string {
        return this.payload.dataset_id;
    }
    get title(): string {
        return this.payload.title;
    }
    get collectionName(): string {
        return this.payload.collection_name;
    }
    get tissues(): string[] {
        return this.payload.tissues;
    }
    get diseases(): string[] {
        return this.payload.diseases;
    }
    get assays(): string[] {
        return this.payload.assays;
    }
    get organisms(): string[] {
        return this.payload.organisms;
    }
    get landingPageUrl(): string {
        return this.payload.landing_page_url;
    }
    get publicationDoi(): string {
        return this.payload.publication_doi;
    }

    get cellCountLabel(): string {
        const count = this.payload.cell_count;
        if (!count) {
            return "unknown size";
        }
        return count >= 1000 ? `${Math.round(count / 1000)}k cells` : `${count} cells`;
    }

    get fileSizeLabel(): string | null {
        const megabytes = this.payload.file_size_megabytes;
        if (megabytes === null) {
            return null;
        }
        return megabytes >= 1024
            ? `${(megabytes / 1024).toFixed(1)} GB`
            : `${Math.round(megabytes)} MB`;
    }

    /** A catalogue name proposed from the title, matching the backend's rules. */
    suggestedCatalogueName(): string {
        return this.title
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "_")
            .replace(/^_+|_+$/g, "")
            .slice(0, 40)
            .replace(/_+$/g, "");
    }
}

export interface ColumnCandidatePayload {
    column_name: string;
    score: number;
    is_known_name: boolean;
    is_usable: boolean;
    distinct_value_count: number;
    total_cells: number;
    missing_fraction: number;
    most_frequent_values: { value: string; count: number }[];
    reasons: string[];
}

/** One observation column, with enough detail to judge it by eye. */
export class ColumnCandidate {
    readonly columnName: string;
    readonly score: number;
    readonly isKnownName: boolean;
    readonly isUsable: boolean;
    readonly distinctValueCount: number;
    readonly totalCells: number;
    readonly missingFraction: number;
    readonly mostFrequentValues: { value: string; count: number }[];
    readonly reasons: string[];

    constructor(payload: ColumnCandidatePayload) {
        this.columnName = payload.column_name;
        this.score = payload.score;
        this.isKnownName = payload.is_known_name;
        this.isUsable = payload.is_usable;
        this.distinctValueCount = payload.distinct_value_count;
        this.totalCells = payload.total_cells;
        this.missingFraction = payload.missing_fraction;
        this.mostFrequentValues = payload.most_frequent_values;
        this.reasons = payload.reasons;
    }

    get missingPercentLabel(): string {
        return `${Math.round(this.missingFraction * 100)}%`;
    }

    /** The three most common labels, for the preview column. */
    get previewValues(): string[] {
        return this.mostFrequentValues.slice(0, 3).map((entry) => entry.value);
    }
}

export interface CellTypeDecision {
    jobId: string;
    datasetTitle: string;
    recommendedColumn: string | null;
    candidates: ColumnCandidate[];
}

export interface ImportJobPayload {
    job_id: string;
    stage: string;
    status: string;
    completed_percent: number;
    message: string;
    error_message: string | null;
    dataset_title: string;
    source: string;
    catalogue_name: string;
    is_waiting_for_user: boolean;
    download_percent: number;
    downloaded_megabytes: number;
    expected_megabytes: number | null;
    cell_count: number | null;
    gene_count: number | null;
    selected_cell_type_column: string | null;
    distinct_cell_type_count: number | null;
    published_file_name: string | null;
    created_at: number;
    updated_at: number;
}

/** Progress of one dataset import. */
export class ImportJob {
    readonly jobId: string;
    readonly stage: string;
    readonly status: string;
    readonly completedPercent: number;
    readonly message: string;
    readonly errorMessage: string | null;
    readonly datasetTitle: string;
    readonly catalogueName: string;
    readonly isWaitingForUser: boolean;
    readonly downloadPercent: number;
    readonly downloadedMegabytes: number;
    readonly expectedMegabytes: number | null;
    readonly cellCount: number | null;
    readonly geneCount: number | null;
    readonly selectedCellTypeColumn: string | null;
    readonly distinctCellTypeCount: number | null;
    readonly publishedFileName: string | null;
    readonly createdAt: Date;

    constructor(payload: ImportJobPayload) {
        this.jobId = payload.job_id;
        this.stage = payload.stage;
        this.status = payload.status;
        this.completedPercent = payload.completed_percent;
        this.message = payload.message;
        this.errorMessage = payload.error_message;
        this.datasetTitle = payload.dataset_title;
        this.catalogueName = payload.catalogue_name;
        this.isWaitingForUser = payload.is_waiting_for_user;
        this.downloadPercent = payload.download_percent;
        this.downloadedMegabytes = payload.downloaded_megabytes;
        this.expectedMegabytes = payload.expected_megabytes;
        this.cellCount = payload.cell_count;
        this.geneCount = payload.gene_count;
        this.selectedCellTypeColumn = payload.selected_cell_type_column;
        this.distinctCellTypeCount = payload.distinct_cell_type_count;
        this.publishedFileName = payload.published_file_name;
        this.createdAt = new Date(payload.created_at * 1000);
    }

    get isActive(): boolean {
        return !["finished", "failed", "cancelled"].includes(this.stage);
    }

    get isFinished(): boolean {
        return this.stage === "finished";
    }

    get hasFailed(): boolean {
        return this.stage === "failed";
    }

    /** Whether polling should continue: paused imports need a person, not a poll. */
    get shouldBePolled(): boolean {
        return this.isActive && !this.isWaitingForUser;
    }

    get stageLabel(): string {
        const labels: Record<string, string> = {
            queued: "Queued",
            downloading: "Downloading",
            inspecting: "Reading the metadata",
            awaiting_cell_type_column: "Waiting for your confirmation",
            converting: "Converting for anndata 0.7.6",
            verifying: "Verifying",
            publishing: "Publishing",
            finished: "Finished",
            failed: "Failed",
            cancelled: "Cancelled",
        };
        return labels[this.stage] ?? this.stage;
    }
}

/** Searching for and importing datasets; administrators only. */
export class DatasetImportApi {
    constructor(private readonly httpClient: HttpClient) {}

    async search(
        source: DatasetSourceName,
        query: string,
        organism: string | null,
        limit = 40,
    ): Promise<RemoteDataset[]> {
        const payloads = await this.httpClient.post<RemoteDatasetPayload[]>(
            "/dataset-import/search",
            { source, query, organism, limit },
        );
        return payloads.map((payload) => new RemoteDataset(payload));
    }

    async startImport(dataset: RemoteDataset, catalogueName: string): Promise<ImportJob> {
        const payload = await this.httpClient.post<ImportJobPayload>(
            "/dataset-import/jobs",
            { dataset: dataset.payload, catalogue_name: catalogueName },
        );
        return new ImportJob(payload);
    }

    async listImports(): Promise<ImportJob[]> {
        const payloads = await this.httpClient.get<ImportJobPayload[]>(
            "/dataset-import/jobs",
        );
        return payloads.map((payload) => new ImportJob(payload));
    }

    async getImport(jobId: string): Promise<ImportJob> {
        const payload = await this.httpClient.get<ImportJobPayload>(
            `/dataset-import/jobs/${encodeURIComponent(jobId)}`,
        );
        return new ImportJob(payload);
    }

    async getCellTypeDecision(jobId: string): Promise<CellTypeDecision> {
        const response = await this.httpClient.get<{
            job_id: string;
            dataset_title: string;
            recommended_column: string | null;
            candidates: ColumnCandidatePayload[];
        }>(`/dataset-import/jobs/${encodeURIComponent(jobId)}/cell-type-column`);

        return {
            jobId: response.job_id,
            datasetTitle: response.dataset_title,
            recommendedColumn: response.recommended_column,
            candidates: response.candidates.map((payload) => new ColumnCandidate(payload)),
        };
    }

    async confirmCellTypeColumn(jobId: string, columnName: string): Promise<ImportJob> {
        const payload = await this.httpClient.post<ImportJobPayload>(
            `/dataset-import/jobs/${encodeURIComponent(jobId)}/cell-type-column`,
            { column_name: columnName },
        );
        return new ImportJob(payload);
    }

    async cancelImport(jobId: string): Promise<void> {
        await this.httpClient.delete(`/dataset-import/jobs/${encodeURIComponent(jobId)}`);
    }
}
