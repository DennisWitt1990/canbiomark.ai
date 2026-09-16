import { AdministrationApi } from "./AdministrationApi";
import { AiSuiteApi } from "./AiSuiteApi";
import { AuthenticationApi } from "./AuthenticationApi";
import { CellSelectionApi } from "./CellSelectionApi";
import { DatasetImportApi } from "./DatasetImportApi";
import { HttpClient } from "./HttpClient";
import { TissueGeneratorApi } from "./TissueGeneratorApi";
import { WorkspaceApi } from "./WorkspaceApi";

/**
 * Composition root of the frontend.
 *
 * One {@link HttpClient} is shared by every API class, so cookie handling, the
 * base URL and error translation are configured in exactly one place.
 */
export class ApiRegistry {
    readonly authentication: AuthenticationApi;
    readonly administration: AdministrationApi;
    readonly cellSelection: CellSelectionApi;
    readonly datasetImport: DatasetImportApi;
    readonly tissueGenerator: TissueGeneratorApi;
    readonly aiSuite: AiSuiteApi;
    readonly workspace: WorkspaceApi;

    constructor(httpClient: HttpClient = new HttpClient()) {
        this.authentication = new AuthenticationApi(httpClient);
        this.administration = new AdministrationApi(httpClient);
        this.cellSelection = new CellSelectionApi(httpClient);
        this.datasetImport = new DatasetImportApi(httpClient);
        this.tissueGenerator = new TissueGeneratorApi(httpClient);
        this.aiSuite = new AiSuiteApi(httpClient);
        this.workspace = new WorkspaceApi(httpClient);
    }
}

/** The instance the whole application uses. */
export const apiRegistry = new ApiRegistry();
