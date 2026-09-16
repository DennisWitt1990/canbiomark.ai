import type { HttpClient } from "./HttpClient";

/** Download links and file listings for the caller's own workspace. */
export class WorkspaceApi {
    constructor(private readonly httpClient: HttpClient) {}

    /** URL of a file in the caller's workspace, for a plain `<a href>`. */
    buildDownloadUrl(relativePath: string): string {
        return this.httpClient.buildUrl("/workspace/download", { path: relativePath });
    }

    async listFiles(
        directory = ".",
    ): Promise<{ directory: string; files: string[]; usedBytes: number }> {
        const response = await this.httpClient.get<{
            directory: string;
            files: string[];
            used_bytes: number;
        }>("/workspace/files", { params: { directory } });

        return {
            directory: response.directory,
            files: response.files,
            usedBytes: response.used_bytes,
        };
    }
}
