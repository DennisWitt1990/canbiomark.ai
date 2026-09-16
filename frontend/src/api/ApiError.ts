import axios from "axios";

/**
 * A request failure translated into something that can be shown to a user.
 *
 * The backend reports every expected problem as `{ "detail": "..." }`, so this
 * class knows where to look and falls back sensibly when it does not find it.
 */
export class ApiError extends Error {
    readonly statusCode: number | null;
    readonly isUnauthenticated: boolean;
    readonly isForbidden: boolean;

    constructor(message: string, statusCode: number | null) {
        super(message);
        this.name = "ApiError";
        this.statusCode = statusCode;
        this.isUnauthenticated = statusCode === 401;
        this.isForbidden = statusCode === 403;
    }

    /** Build an {@link ApiError} from anything a failed request threw. */
    static from(cause: unknown, fallbackMessage = "The request failed."): ApiError {
        if (cause instanceof ApiError) {
            return cause;
        }

        if (axios.isAxiosError(cause)) {
            const statusCode = cause.response?.status ?? null;
            return new ApiError(
                ApiError.readDetail(cause.response?.data) ?? cause.message ?? fallbackMessage,
                statusCode,
            );
        }

        if (cause instanceof Error) {
            return new ApiError(cause.message || fallbackMessage, null);
        }

        return new ApiError(fallbackMessage, null);
    }

    /** Pull the human-readable message out of a FastAPI error body. */
    private static readDetail(responseBody: unknown): string | null {
        if (typeof responseBody === "string" && responseBody.trim()) {
            return responseBody.trim();
        }
        if (!responseBody || typeof responseBody !== "object") {
            return null;
        }

        const detail = (responseBody as { detail?: unknown }).detail;
        if (typeof detail === "string" && detail.trim()) {
            return detail.trim();
        }
        if (Array.isArray(detail)) {
            // FastAPI validation errors arrive as a list of issue objects.
            const messages = detail
                .map((issue) =>
                    issue && typeof issue === "object" && "msg" in issue
                        ? String((issue as { msg: unknown }).msg)
                        : null,
                )
                .filter((message): message is string => Boolean(message));
            if (messages.length > 0) {
                return messages.join("\n");
            }
        }
        return null;
    }
}
