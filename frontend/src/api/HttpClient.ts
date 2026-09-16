import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios";
import { ApiError } from "./ApiError";

/** Resolve the API base URL from the build-time environment. */
function resolveBaseUrl(): string {
    const configuredUrl = import.meta.env.VITE_API_URL?.trim();
    if (configuredUrl) {
        return `${configuredUrl.replace(/\/+$/, "")}/api`;
    }
    // The backend serves the built frontend from the same origin.
    return "/api";
}

/**
 * The single HTTP entry point of the frontend.
 *
 * Every API class receives an instance of this and therefore inherits the same
 * cookie handling, base URL and error translation. `withCredentials` is always
 * on, because the session lives in an HttpOnly cookie.
 */
export class HttpClient {
    private readonly axiosInstance: AxiosInstance;

    constructor(baseUrl: string = resolveBaseUrl()) {
        this.axiosInstance = axios.create({
            baseURL: baseUrl,
            withCredentials: true,
            headers: { "Content-Type": "application/json" },
        });
    }

    /** Absolute base URL, used to build plain `<a href>` download links. */
    get baseUrl(): string {
        const configuredBase = this.axiosInstance.defaults.baseURL ?? "/api";
        if (/^https?:\/\//i.test(configuredBase)) {
            return configuredBase;
        }
        return `${window.location.origin}${configuredBase.startsWith("/") ? "" : "/"}${configuredBase}`;
    }

    async get<TResponse>(path: string, config?: AxiosRequestConfig): Promise<TResponse> {
        return this.request<TResponse>(() => this.axiosInstance.get<TResponse>(path, config));
    }

    async post<TResponse>(
        path: string,
        body?: unknown,
        config?: AxiosRequestConfig,
    ): Promise<TResponse> {
        return this.request<TResponse>(() =>
            this.axiosInstance.post<TResponse>(path, body, config),
        );
    }

    async patch<TResponse>(path: string, body?: unknown): Promise<TResponse> {
        return this.request<TResponse>(() => this.axiosInstance.patch<TResponse>(path, body));
    }

    async delete<TResponse>(path: string, config?: AxiosRequestConfig): Promise<TResponse> {
        return this.request<TResponse>(() =>
            this.axiosInstance.delete<TResponse>(path, config),
        );
    }

    /** Upload multipart form data, optionally reporting progress. */
    async postFormData<TResponse>(
        path: string,
        formData: FormData,
        onProgressPercent?: (percent: number) => void,
    ): Promise<TResponse> {
        return this.request<TResponse>(() =>
            this.axiosInstance.post<TResponse>(path, formData, {
                headers: { "Content-Type": "multipart/form-data" },
                onUploadProgress: (event) => {
                    if (!onProgressPercent || !event.total) {
                        return;
                    }
                    onProgressPercent(Math.round((event.loaded / event.total) * 100));
                },
            }),
        );
    }

    /** Build a URL for a link the browser downloads directly. */
    buildUrl(path: string, queryParameters: Record<string, string> = {}): string {
        const query = new URLSearchParams(queryParameters).toString();
        const normalizedPath = path.startsWith("/") ? path : `/${path}`;
        return `${this.baseUrl}${normalizedPath}${query ? `?${query}` : ""}`;
    }

    private async request<TResponse>(
        send: () => Promise<{ data: TResponse }>,
    ): Promise<TResponse> {
        try {
            const response = await send();
            return response.data;
        } catch (cause) {
            throw ApiError.from(cause);
        }
    }
}
