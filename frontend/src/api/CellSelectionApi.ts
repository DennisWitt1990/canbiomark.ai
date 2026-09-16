import type { HttpClient } from "./HttpClient";

export interface ExperimentPayload {
    experiment_id: number;
    experiment_name: string;
    tissue_name: string;
    catalogue_file_name: string;
    display_label: string;
}

/** One selectable experiment from the shared catalogue. */
export class Experiment {
    readonly experimentId: number;
    readonly experimentName: string;
    readonly tissueName: string;
    readonly displayLabel: string;

    constructor(payload: ExperimentPayload) {
        this.experimentId = payload.experiment_id;
        this.experimentName = payload.experiment_name;
        this.tissueName = payload.tissue_name;
        this.displayLabel = payload.display_label;
    }

    /** Case-insensitive match against tissue and experiment name. */
    matches(searchTerm: string): boolean {
        const normalizedTerm = searchTerm.trim().toLowerCase();
        if (!normalizedTerm) {
            return true;
        }
        return `${this.tissueName} ${this.experimentName}`
            .toLowerCase()
            .includes(normalizedTerm);
    }
}

export interface MergeResult {
    mergedPath: string;
    cellTypesByExperiment: Record<string, string[]>;
}

export interface CellTypePreview {
    experimentIds: number[];
    cellTypesByExperiment: Record<string, string[]>;
}

/** The cell selector workflow. */
export class CellSelectionApi {
    constructor(private readonly httpClient: HttpClient) {}

    async listExperiments(): Promise<Experiment[]> {
        const payloads = await this.httpClient.get<ExperimentPayload[]>(
            "/cell-selection/experiments",
        );
        return payloads.map((payload) => new Experiment(payload));
    }

    async previewCellTypes(experimentIds: number[]): Promise<CellTypePreview> {
        const response = await this.httpClient.post<{
            cell_types_by_experiment: Record<string, string[]>;
        }>("/cell-selection/cell-types", { experiment_ids: experimentIds });
        return { experimentIds, cellTypesByExperiment: response.cell_types_by_experiment };
    }

    async createSelectedDataset(experimentIds: number[], selectedCellTypes: Record<string, string[]>): Promise<string> {
        const response = await this.httpClient.post<{ final_path: string }>(
            "/cell-selection/select",
            { experiment_ids: experimentIds, selected_cell_types: selectedCellTypes },
        );
        return response.final_path;
    }

    async mergeExperiments(experimentIds: number[]): Promise<MergeResult> {
        const response = await this.httpClient.post<{
            merged_path: string;
            cell_types_by_experiment: Record<string, string[]>;
        }>("/cell-selection/merge", { experiment_ids: experimentIds });

        return {
            mergedPath: response.merged_path,
            cellTypesByExperiment: response.cell_types_by_experiment,
        };
    }

    async filterCellTypes(
        mergedPath: string,
        selectedCellTypes: Record<string, string[]>,
    ): Promise<string> {
        const response = await this.httpClient.post<{ final_path: string }>(
            "/cell-selection/filter",
            { merged_path: mergedPath, selected_cell_types: selectedCellTypes },
        );
        return response.final_path;
    }
}
