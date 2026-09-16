import type { HttpClient } from "./HttpClient";
import type { UserRoleName } from "./AuthenticationApi";

export interface ManagedUserPayload {
    user_id: string;
    username: string;
    display_name: string;
    role: UserRoleName;
    is_active: boolean;
    must_change_password: boolean;
    quota_bytes: number;
    quota_gigabytes: number;
    used_bytes: number;
    quota_used_percent: number;
    active_session_count: number;
    created_at: string;
    last_login_at: string | null;
}

/** One row of the user administration table. */
export class ManagedUser {
    readonly userId: string;
    readonly username: string;
    readonly displayName: string;
    readonly role: UserRoleName;
    readonly isActive: boolean;
    readonly mustChangePassword: boolean;
    readonly quotaGigabytes: number;
    readonly usedBytes: number;
    readonly quotaUsedPercent: number;
    readonly activeSessionCount: number;
    readonly createdAt: Date;
    readonly lastLoginAt: Date | null;

    constructor(payload: ManagedUserPayload) {
        this.userId = payload.user_id;
        this.username = payload.username;
        this.displayName = payload.display_name || payload.username;
        this.role = payload.role;
        this.isActive = payload.is_active;
        this.mustChangePassword = payload.must_change_password;
        this.quotaGigabytes = payload.quota_gigabytes;
        this.usedBytes = payload.used_bytes;
        this.quotaUsedPercent = payload.quota_used_percent;
        this.activeSessionCount = payload.active_session_count;
        this.createdAt = new Date(payload.created_at);
        this.lastLoginAt = payload.last_login_at ? new Date(payload.last_login_at) : null;
    }

    get isAdministrator(): boolean {
        return this.role === "administrator";
    }

    /** Human readable disk usage, e.g. `1.4 GB`. */
    get usedDiskLabel(): string {
        const megabytes = this.usedBytes / (1024 * 1024);
        if (megabytes < 1) {
            return `${(this.usedBytes / 1024).toFixed(0)} KB`;
        }
        if (megabytes < 1024) {
            return `${megabytes.toFixed(1)} MB`;
        }
        return `${(megabytes / 1024).toFixed(2)} GB`;
    }

    get statusLabel(): string {
        if (!this.isActive) {
            return "disabled";
        }
        return this.mustChangePassword ? "password reset pending" : "active";
    }
}

export interface CreateUserInput {
    username: string;
    displayName: string;
    role: UserRoleName;
    quotaGigabytes: number | null;
    initialPassword: string | null;
    requirePasswordChange: boolean;
}

export interface UpdateUserInput {
    displayName?: string;
    role?: UserRoleName;
    quotaGigabytes?: number;
    isActive?: boolean;
}

export interface UserSession {
    session_id_preview: string;
    created_at: string;
    expires_at: string;
    last_seen_at: string | null;
    client_description: string;
}

export interface AuditEvent {
    event_id: number;
    occurred_at: string;
    actor_username: string | null;
    action: string;
    subject: string | null;
    detail: string;
}

/** Everything the administration screens need. */
export class AdministrationApi {
    constructor(private readonly httpClient: HttpClient) {}

    async listUsers(): Promise<ManagedUser[]> {
        const response = await this.httpClient.get<{ users: ManagedUserPayload[] }>(
            "/admin/users",
        );
        return response.users.map((payload) => new ManagedUser(payload));
    }

    async createUser(
        input: CreateUserInput,
    ): Promise<{ user: ManagedUser; initialPassword: string }> {
        const response = await this.httpClient.post<{
            user: ManagedUserPayload;
            initial_password: string;
        }>("/admin/users", {
            username: input.username,
            display_name: input.displayName,
            role: input.role,
            quota_gigabytes: input.quotaGigabytes,
            initial_password: input.initialPassword,
            require_password_change: input.requirePasswordChange,
        });
        return {
            user: new ManagedUser(response.user),
            initialPassword: response.initial_password,
        };
    }

    async updateUser(userId: string, input: UpdateUserInput): Promise<ManagedUser> {
        const payload = await this.httpClient.patch<ManagedUserPayload>(
            `/admin/users/${encodeURIComponent(userId)}`,
            {
                display_name: input.displayName,
                role: input.role,
                quota_gigabytes: input.quotaGigabytes,
                is_active: input.isActive,
            },
        );
        return new ManagedUser(payload);
    }

    async resetPassword(
        userId: string,
        newPassword: string | null,
        requirePasswordChange: boolean,
    ): Promise<string> {
        const response = await this.httpClient.post<{ new_password: string }>(
            `/admin/users/${encodeURIComponent(userId)}/password`,
            { new_password: newPassword, require_password_change: requirePasswordChange },
        );
        return response.new_password;
    }

    async listSessions(userId: string): Promise<UserSession[]> {
        return this.httpClient.get<UserSession[]>(
            `/admin/users/${encodeURIComponent(userId)}/sessions`,
        );
    }

    async revokeSessions(userId: string): Promise<number> {
        const response = await this.httpClient.delete<{ revoked_session_count: number }>(
            `/admin/users/${encodeURIComponent(userId)}/sessions`,
        );
        return response.revoked_session_count;
    }

    async deleteUser(userId: string, deleteWorkspace: boolean): Promise<void> {
        await this.httpClient.delete(`/admin/users/${encodeURIComponent(userId)}`, {
            params: { delete_workspace: deleteWorkspace },
        });
    }

    async listAuditEvents(limit = 100): Promise<AuditEvent[]> {
        return this.httpClient.get<AuditEvent[]>("/admin/audit", { params: { limit } });
    }
}
